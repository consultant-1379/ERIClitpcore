import json

from urlparse import urlunsplit
from urllib import urlencode
from httplib import HTTPException
from collections import defaultdict
from urllib2 import urlopen, URLError
from litp.core.litp_logging import LitpLogger

log = LitpLogger()


class PuppetDbApi(object):
    '''Performs a PuppetDB API request.'''

    def __init__(self):
        self.host_string = "localhost:8080"
        self.api_version = "v3"
        self.protocol = "http"

    def check_for_feedback(self, hostname, config_version, puppet_phase):
        certname = hostname.lower()
        reports = self._get_reports(certname, config_version)
        if reports:
            report_events = self._get_report_events(reports)
            known_tasks_dict, failed_taskless_event = \
                    self._get_reports_resources(report_events)
            tasks_report = self._build_report(known_tasks_dict)
            eventless_tasks = self._get_eventless_tasks(known_tasks_dict,
                    puppet_phase)
            if eventless_tasks:
                # Generate feedback for phase tasks resources without events
                all_resources = self._get_node_resources(certname)
                eventless_tasks_report = self._build_no_event_report(
                    all_resources, known_tasks_dict
                )
                tasks_report += eventless_tasks_report
            return (
                certname, config_version, tasks_report, failed_taskless_event
            )

    def _query(self, endpoint, query):
        params = urlencode({'query': json.dumps(query)})
        url = urlunsplit((self.protocol, self.host_string,
            '/'.join([self.api_version, endpoint]), params, None))
        try:
            response = urlopen(url)
            str_data = response.read()
            response.close()
            return json.loads(str_data)
        except (URLError, HTTPException) as exception:
            log.event.error(
                "A problem occurred while querying PuppetDb: {0}".format(
                exception))
            return []
        except (ValueError, TypeError) as exception:
            log.event.error("Unexpected response from PuppetDb: {0}".format(
                exception))
            return []
        except Exception as exception:
            log.event.error("Could not query PuppetDb: {0}".format(exception))
            return []

    def _get_reports(self, certname, config_version):
        eq_cert_params = ["=", "certname", certname]
        return [report for report in self._query("reports", eq_cert_params)
            if self.check_config_version(
                    report['configuration-version'], config_version)]

    @staticmethod
    def check_config_version(report_version, written_version):
        """Check if the queried report matches the version we're looking for.

        Look for greater than or equal to the writen version as another process
        may have incremented and run puppet already, picking up these changes
        """
        try:
            return int(report_version) >= written_version
        except (ValueError, TypeError):
            return False

    def _get_report_events(self, reports):
        # An event relates to a change made to a individual resources property.
        # Legal event status are success, fail, noop and skipped
        report_events = []
        for report in reports:
            eq_report_params = ["=", "report", report["hash"]]
            report_events.extend(self._query("events", eq_report_params))
        return report_events

    def _get_reports_resources(self, report_events):
        resources_cache = {}  # {(title, type, certname): {resource}}
        known_tasks_dict = defaultdict(list)  # {(uid, uuid):(resource, state)}

        found_taskless_failed_event = False
        for event in report_events:
            event_resource = None
            unique_key = (
                event["resource-title"],
                event["resource-type"],
                event["certname"]
            )
            if unique_key in resources_cache:
                event_resource = resources_cache[unique_key]
            else:
                eq_resource_params = ["and",
                    ["=", "title", event["resource-title"]],
                    ["=", "type", event["resource-type"]],
                    ["=", "certname", event["certname"]]
                ]
                result = self._query("resources", eq_resource_params)
                if result:
                    event_resource = result[0]
                    resources_cache[unique_key] = event_resource

            event_outcome = "success" if event["status"] == "success" \
                    else "fail"
            if event_resource is not None:
                task_uids_key = self._get_task_uids(event_resource)
                if None not in task_uids_key:
                    # Multiple resources may have the same ConfigTask uids tag
                    known_tasks_dict[task_uids_key].append(
                        (event_resource, event_outcome))
            elif event["status"] == "failure":
                found_taskless_failed_event = True

        return known_tasks_dict, found_taskless_failed_event

    def _get_eventless_tasks(self, known_tasks_dict, phase):
        eventless_tasks = []
        for task in phase:
            unique_id = "task_%s" % task.unique_id
            uuid = "tuuid_%s" % task.uuid
            if (unique_id, uuid) not in known_tasks_dict:
                eventless_tasks.append(task)
        return eventless_tasks

    def _get_node_resources(self, certname):
        eq_certname_params = ["=", "certname", certname]
        return self._query("resources", eq_certname_params)

    @staticmethod
    def _get_task_uids(resource):
        uid = None
        uuid = None
        for tag in resource["tags"]:
            if tag.startswith("task_"):
                uid = tag
            elif tag.startswith("tuuid_"):
                uuid = tag
            if None not in (uid, uuid):
                break
        return uid, uuid

    def _build_report(self, known_tasks_dict):
        tasks_report = []
        for task_resources in known_tasks_dict.itervalues():
            # The first resource is arbitrarily chosen to represent its task
            first_task_resource = task_resources[0][0]
            if all(state == "success" for (resource, state) in task_resources):
                tasks_report.append(
                    self._build_task_report(first_task_resource, "success")
                )
            else:
                tasks_report.append(
                    self._build_task_report(first_task_resource, "fail")
                )
        return "".join(tasks_report)

    def _build_no_event_report(self, all_resources, known_tasks_dict):
        tasks_report = []
        for resource in all_resources:
            # Don't allow uids of None from resources like known_tasks_dict
            uids = self._get_task_uids(resource)
            if None in uids or uids in known_tasks_dict:
                continue
            tasks_report.append(self._build_task_report(resource, "success"))
        return "".join(tasks_report)

    def _build_task_report(self, resource, state):
        task_report = ""
        uid, uuid = self._get_task_uids(resource)
        task_report = "litp_feedback:%s:%s=%s," % (uid, uuid, state)
        return task_report
