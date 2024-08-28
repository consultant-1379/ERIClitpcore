#!/usr/bin/python
'''
##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
'''
import sys
import argparse
import ConfigParser
from collections import OrderedDict
from Crypto.Cipher import AES
from base64 import standard_b64encode, standard_b64decode
from os import chmod, chown, path, getuid
from grp import getgrnam
from pwd import getpwnam
import getpass
SECURITY_CONF_FILE_PATH = "/etc/litp_security.conf"


def pad(data, padding=16):
    p = (padding - (len(data) - 1) % padding) - 1
    return data + chr(3) * p


class LitpCrypter(object):

    def __init__(self):
        parser = ConfigParser.SafeConfigParser(dict_type=OrderedDict)
        parser.read(SECURITY_CONF_FILE_PATH)
        self.keyset = parser.get("keyset", "path")
        self.password_file_path = parser.get("password", "path")
        self.args = None

    def _encrypt(self, data=''):
        """Encrypt data and then base-64 encode it
        @param data: data to encrypt
        @type data: string"""
        with open(self.keyset, 'r') as f:
            key = standard_b64decode(f.readlines()[0])

        encryptor = AES.new(key, AES.MODE_CFB, '0' * AES.block_size,
                            segment_size=128)

        return standard_b64encode(encryptor.encrypt(pad(data)))

    def send_messages_to_stderr(self, msg_list):
        for message in msg_list:
            sys.stderr.write("%s\n" % message)

    def set_password(self, args):
        try:
            err = False
            service = args.service
            user = args.user
            b64_user = standard_b64encode(user).replace('=', '')

            messages = []

            if args.password and args.pass_prompt:
                messages.append("unrecognized arguments: " +
                "%s. password not needed with --prompt" % self.args.password)
                err = True

            if args.pass_prompt and not err:
                pw1 = ""
                pw2 = "b"
                flag_first = True
                while pw1 != pw2:
                    if flag_first:
                        flag_first = False
                    else:
                        print "passwords don't match"
                        pw1 = ""
                    while not pw1:
                        pw1 = getpass.getpass()
                        if not pw1:
                            print "Error: password must not be empty"
                    pw2 = getpass.getpass("Confirm password:")
            else:
                pw1 = args.password
            password = pw1

            args_dict = dict(zip(("service", "user", "password"),
                            (service, user, password)))

            for k, v in args_dict.items():
                if not v:
                    messages.append("Error: %s must not be empty" % k)
                    err = True

            if not err:

                cp = ConfigParser.SafeConfigParser(dict_type=OrderedDict)
                cp.optionxform = str
                cp.read(self.password_file_path)
                if not cp.has_section(service):
                    cp.add_section(service)
                enc_password = self._encrypt(password)

                if cp.has_option(service, user):
                    cp.remove_option(service, user)

                cp.set(service, b64_user, enc_password)
                with open(self.password_file_path, 'wb') as password_file:
                    cp.write(password_file)

                if getuid() == 0:
                    if path.exists(self.password_file_path):
                        chmod(self.password_file_path, 0o664)
                        # user root, group litp-admin
                        chown(self.password_file_path, getpwnam("root").pw_uid,
                              getgrnam("litp-admin").gr_gid)

        except (IOError, IndexError, TypeError) as e:
            messages.append("Error in writing to %s" % self.password_file_path)
        except OSError as e:
            messages.append("%s" % e)

        finally:
            self.send_messages_to_stderr(messages)
            if messages:
                sys.exit(1)

    def delete_password(self, args):
        err = False
        service = args.service
        user = args.user
        messages = []
        args_dict = dict(zip(("service", "user"),
                            (service, user)))

        for k, v in args_dict.items():
            if not v:
                messages.append("Error: %s must not be empty" % k)
                err = True

        if err:
            self.send_messages_to_stderr(messages)
            sys.exit(1)

        cp = ConfigParser.SafeConfigParser(dict_type=OrderedDict)
        cp.optionxform = str
        cp.read(self.password_file_path)
        b64_user = standard_b64encode(user).replace('=', '')

        if not cp.has_section(service):
            messages.append("Given service does not exist")

        elif not cp.has_option(service, b64_user):
            if not cp.has_option(service, user):
                messages.append("Given username does not exist")

        if not messages:
            if len(cp.options(service)) == 1:
                cp.remove_section(service)
            else:
                if not cp.has_option(service, b64_user):
                    cp.remove_option(service, user)
                else:
                    cp.remove_option(service, b64_user)

            with open(self.password_file_path, 'wb') as password_file:
                cp.write(password_file)
        else:
            self.send_messages_to_stderr(messages)
            sys.exit(1)

    def run(self, args):
        parser = argparse.ArgumentParser(
            description="litpcrypt command line interface to manage passwords"
                        " required by LITP service."
        )
        subparsers = parser.add_subparsers(
            title='actions',
            description=(
                "Actions to execute on stored passwords.\n"
                "For more detailed information on each action enter "
                "the command 'litpcrypt <action> -h'"
            ),
            help="",
            metavar="")

        parser_set = subparsers.add_parser(
            'set',
            help='Add a password to LITP password storage',
            description="set - Add a password to LITP password storage")
        parser_set.set_defaults(func=self.set_password)

        parser_set.add_argument('service',
            help=('keyword uniquely identifying the '
                  'service and host'))

        parser_set.add_argument('user', help=('user'))

        parser_set.add_argument('password', nargs='?',
                                 help=('password as an argument '
                                   + 'can\'t be used with prompt'))

        parser_set.add_argument('--prompt', dest="pass_prompt",
                                action="store_true",
                                help=('prompt for password'))

        parser_delete = subparsers.add_parser(
            'delete',
            help='Remove a password from LITP password storage',
            description=("delete - Remove a password from LITP"
                         " password storage"))
        parser_delete.set_defaults(func=self.delete_password)
        parser_delete.add_argument('service',
            help=('keyword uniquely identifying the '
                  'service and host'))

        parser_delete.add_argument('user', help=('user'))

        self.args = parser.parse_args(args)

        return self.args.func(self.args)

if __name__ == "__main__":
    cli = LitpCrypter()
    exit(cli.run(sys.argv[1:]))
