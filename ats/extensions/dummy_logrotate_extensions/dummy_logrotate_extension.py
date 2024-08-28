import re

from litp.core.model_type import ItemType
from litp.core.model_type import Collection
from litp.core.model_type import Property
from litp.core.model_type import PropertyType
from litp.core.extension import ModelExtension
from litp.core.validators import PropertyValidator
from litp.core.validators import ValidationError
from litp.core.validators import NotEmptyStringValidator
from litp.core.validators import ItemValidator


class DummyLogrotateExtension(ModelExtension):
    def define_property_types(self):
        return [PropertyType("logrotate_basic_size", regex=r"^\d+[kMG]?$"),
                PropertyType("logrotate_any_string", regex=r"^.+$",
                            validators=[NotEmptyStringValidator()]),
                PropertyType("logrotate_date_format",
                             regex="^([-]?[%]+[Y|m|d|s])*$"),
                PropertyType("logrotate_email", regex=r"[^@]+@[^@]+\.[^@]+"),
                PropertyType("logrotate_time_period", regex=r"^((day)|(week)|"
                "(month)|(year))$"),
                PropertyType("comma_separated_file_names",
                             regex=r"([^,])+(,([^,])+)*",
                             validators=[PathListValidator()])]

    def define_item_types(self):
        return [
            ItemType("logrotate-rule-config",
                extend_item="node-config",
                item_description="A collection of logrotate-rule items. "
                     "Update and remove reconfiguration actions are "
                     "currently supported for this item type.",
                rules=Collection("logrotate-rule", min_count=1)
            ),
            ItemType("logrotate-rule",
                item_description="A logrotate rule to be configured "
                     "on a node.",
                     validators=[MailFirstAndMailLastValidator()],
               name=Property("basic_string",
                    prop_description="The String name of the rule."
                                     " It must be unique per node in "
                                     "the deployment",
                    required=True,
                    updatable_plugin=False,
                    updatable_rest=False),

                path=Property("comma_separated_file_names",
                    prop_description=(
                        "Comma separated path Strings to the"
                        " log file(s) to be rotated."
                    ),
                    required=True
                ),
                compress=Property("basic_boolean",
                    prop_description=(
                        "A Boolean value specifying whether the rotated "
                        "logs should be compressed (optional)."
                    )
                ),
                compresscmd=Property("logrotate_any_string",
                    prop_description=(
                        "The command String that should be executed to "
                        "compress the rotated logs (optional)."
                        ),
                ),
                compressext=Property("basic_string",
                    prop_description=(
                        "The extension String to be appended to the rotated "
                        "log files after they have been compressed (optional)."
                    )
                ),
                compressoptions=Property("basic_string",
                    prop_description=(
                        "A String of command line options to be passed to "
                        "the compression program specified in `compresscmd` "
                        "(optional)."
                    )
                ),
                copy=Property("basic_boolean",
                    prop_description=(
                        "A Boolean specifying whether logrotate should "
                        "just take a copy of the log file and not touch "
                        "the original (optional)."
                    )
                ),
                copytruncate=Property("basic_boolean",
                    prop_description=(
                        "A Boolean specifying whether logrotate should "
                        "truncate the original log file after taking "
                        "a copy (optional)."
                    )
                ),
                create=Property("basic_boolean",
                    prop_description=(
                        "A Boolean specifying whether logrotate should create "
                        "a new log file immediately after rotation (optional)."
                    )
                ),
                create_mode=Property("file_mode",
                    prop_description=(
                        "An octal mode String logrotate should apply to "
                        "the newly created log file if create => true "
                        "(optional). You must define a value for the "
                        "**create** property if you include the "
                        "**create_mode** property in your rule."
                        )
                ),
                create_owner=Property("basic_string",
                    prop_description=(
                        "A username String that logrotate should set "
                        "the owner of the newly created log file to if "
                        "create => true (optional). You must define a value "
                        "for the **create_mode** property if you include the "
                        "**create_owner** property in your rule."
                    )
                ),
                create_group=Property("basic_string",
                    prop_description=(
                        "A String group name that logrotate should apply "
                        "to the newly created log file if create => true "
                        "(optional). You must define a value "
                        "for the **create_owner** property if you include the "
                        "**create_group** property in your rule."
                    )
                ),
                dateext=Property("basic_boolean",
                    prop_description=(
                        "A Boolean specifying whether rotated log files "
                        "should be archived by adding a date extension "
                        "rather just a number (optional)."
                    )
                ),
                dateformat=Property("logrotate_date_format",
                    prop_description=(
                        "The format String to be used for `dateext` "
                        "(optional). Valid "
                        "specifiers are \'%Y\', \'%m\', \'%d\' "
                        "and \'%s\'.',"
                    )
                ),
                delaycompress=Property("basic_boolean",
                    prop_description=(
                        "A Boolean specifying whether compression "
                        "of the rotated log file should be delayed until "
                        "the next logrotate run (optional)."
                    )
                ),
                extension=Property("basic_string",
                    prop_description=(
                        "Log files with this extension String are allowed "
                        "to keep it after rotation (optional)."
                    )
                ),
                ifempty=Property("basic_boolean",
                    prop_description=(
                        "A Boolean specifying whether the log file should be "
                        "rotated even if it is empty (optional)."
                    )
                ),
                mail=Property("logrotate_email",
                    prop_description=(
                        "The email address String that logs that are about "
                        "to be rotated out of existence are emailed to "
                        "(optional)."
                    )
                ),
                mailfirst=Property("basic_boolean",
                    prop_description=(
                        "A Boolean that when used with **mail** has logrotate "
                        "email the just rotated file rather than the about "
                        "to expire file (optional). This property and the "
                        "**maillast** property are mutually exclusive."
                    )
                ),
                maillast=Property("basic_boolean",
                    prop_description=(
                        "A Boolean that when used with `mail` has logrotate "
                        "email the about to expire file rather than the "
                        "just rotated file (optional). This property and the "
                        "**maillast** property are mutually exclusive."
                    )
                ),
                maxage=Property("integer",
                    prop_description=(
                        "The Integer maximum number of days that a rotated "
                        "log file can stay on the system (optional)."
                    )
                ),
                minsize=Property("logrotate_basic_size",
                    prop_description=(
                        "The String minimum size a log file must be to be "
                        "rotated, but not before the scheduled rotation time "
                        "(optional). The default units are bytes, append k,M "
                        "or G for kilobytes, megabytes and gigabytes "
                        "respectively."
                    )
                ),
                missingok=Property("basic_boolean",
                    prop_description=(
                        "A Boolean specifying whether logrotate should ignore "
                        "missing log files or issue an error (optional)."
                    )
                ),
                olddir=Property("path_string",
                    prop_description=(
                        "A String path to a directory that rotated logs "
                        "should be moved to (optional)."
                    )
                ),
                postrotate=Property("logrotate_any_string",
                    prop_description=(
                        "A command String that should be executed by "
                        "/bin/sh after the log file is rotated (optional)."
                    )
                ),
                prerotate=Property("logrotate_any_string",
                    prop_description=(
                        "A command String that should be executed by "
                        "/bin/sh before the log file is rotated and only if "
                        "it will be rotated (optional)."
                    )
                ),
                firstaction=Property("logrotate_any_string",
                    prop_description=(
                        "A command String that should be executed by /bin/sh "
                        "once before all log files that match the wildcard "
                        "pattern are rotated (optional)."
                    )
                ),
                lastaction=Property("logrotate_any_string",
                    prop_description=(
                        "A command String that should be execute by /bin/sh "
                        "once after all the log files that match the wildcard "
                        "pattern are rotated (optional)."
                    )
                ),
                rotate=Property("integer",
                    prop_description=(
                        "A The Integer number of rotated log files to "
                        "keep on disk (optional)."
                    )
                ),
                rotate_every=Property("logrotate_time_period",
                    prop_description=(
                        "How often the log files should be rotated as "
                        "a String. Valid values are \'day\', \'week\', "
                        "\'month\' and \'year\' (optional)."
                    )
                ),
                sharedscripts=Property("basic_boolean",
                    prop_description=(
                        "A Boolean specifying whether logrotate should run "
                        "the postrotate and prerotate scripts for each "
                        "matching file or just once (optional)."
                    )
                ),
                shred=Property("basic_boolean",
                    prop_description=(
                        "A Boolean specifying whether logs should be deleted "
                        "with shred instead of unlink (optional)."
                    )
                ),
                shredcycles=Property("integer",
                    prop_description=(
                        "The Integer number of times shred should overwrite "
                        "log files before unlinking them (optional)."
                    )
                ),
                size=Property("logrotate_basic_size",
                    prop_description=(
                        "The String size a log file has to reach before it "
                        "will be rotated (optional). The default units are "
                        "bytes, append k, M or G for kilobytes, megabytes "
                        "or gigabytes respectively."
                    )
                ),
                start=Property("integer",
                    prop_description=(
                        "The Integer number to be used as the base for the "
                        "extensions appended to the rotated log files "
                        "(optional)."
                    )
                ),
                uncompresscmd=Property("logrotate_any_string",
                    prop_description=(
                        "The String command to be used to uncompress log "
                        "files (optional)."
                    )
                )
            )
        ]


class PathListValidator(PropertyValidator):
    """
    Validates that a property value doesn't have quotes \"\
characters in it.
    """

    def __init__(self,):
        """
        """
        super(PathListValidator, self).__init__()

    def validate(self, property_value,):
        escaped_spaces = property_value.replace(r'\ ', '!')
        if len(escaped_spaces.split(" ")) > 1:
            return ValidationError(
                error_message=("Value \"%s\" is not a valid path." %
                               (property_value,))
            )
        for p in property_value.split(","):
            if len(p) < 1 or p.startswith(" ") or p.endswith(" "):
                return ValidationError(
                    error_message=("Value \"" + p + "\" is not a valid path."))
            if not re.match(r"([A-Za-z0-9\-\.\*\s\\_\/#:]+)?", p):
                return ValidationError(
                    error_message=("Value \"" + p + "\" is not a valid path."))


class MailFirstAndMailLastValidator(ItemValidator):
    """
    Validates that the properties "mailfirst"' and "maillast" '
    'can not both be set to true'.
    """

    def __init__(self,):
        """
        """
        super(MailFirstAndMailLastValidator, self).__init__()

    def validate(self, properties):
        errors = []
        mailfirst = 'mailfirst'
        maillast = 'maillast'
        mailfirst_prop = properties.get(mailfirst, '')
        maillast_prop = properties.get(maillast, '')
        if mailfirst_prop == 'true' and maillast_prop == 'true':
            errors = ValidationError(error_message='The properties "mailfirst"'
                        ' and "maillast" can not both be set to true')
        return errors
