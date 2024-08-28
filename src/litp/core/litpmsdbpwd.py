#!/usr/bin/python
'''
##############################################################################
# COPYRIGHT Ericsson AB 2018
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
'''
import sys
import re
import datetime
import argparse
import getpass
import hashlib
import os
import grp
from contextlib import contextmanager
import cherrypy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, String, DateTime, UnicodeText
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import SQLAlchemyError

MAX_PROMPT_TRIES = 3
NUM_PREV_PASSWDS_DISALLOWED = 5

ERR_PASSWORD_BAD = """
{err}

The password must have at least eight characters.
The password must contain at least 1 lower case alpha character.
The password must contain at least 1 upper case alpha character.
The password must contain at least 1 numeric character.
The password must not contain the username.
The password may only contain the following special characters:
    hyphen ( - ), underscore ( _ ), and period (.)
The password may not be a repeat of one of the previous 5 passwords.
"""
ERR_PASSWORD_INVALID = 'Password invalid.'
ERR_PWD_REPEAT = 'Password is repeat of one of the previous 5 passwords.'
WARN_PWD_UPDATE_PENDING = ('Password update pending. Cannot be reset until '
                           'that update is completed.')
WARN_CURR_PWD_MISMATCH = "Password does not match current password"
WARN_EMPTY_PASSWORD = 'Password must not be empty'
WARN_PWD_MISMATCH = "Passwords don't match"

PUPPET_GROUP_NAME = 'puppet'
PP_MODULE_DIR = 'etc/puppet/modules/puppetdb/manifests/'
PP_FILE = 'db_pwd.pp'
PP_FILE_TEMPLATE = """
class puppetdb::db_pwd {{
  $postgres_password = '{0}'
}}
"""

Base = declarative_base()


@contextmanager
def db_session_scope(db_sessionmaker):
    """
    Context manager for db session
    """
    session = db_sessionmaker()
    try:
        yield session
        session.commit()
    except Exception as exc:  # pylint: disable=W0703
        session.rollback()
        session.close()
        sys.stderr.write('{0}Error: {1}\n'.format(('Database '
                         if isinstance(exc, SQLAlchemyError) else ''), exc))
        sys.exit(1)
    finally:
        session.close()


class PgPasswdHist(Base):  # pylint: disable=R0903, W0232
    """
    Class for pg_passwd_hist db table
    """
    __tablename__ = 'pg_passwd_hist'

    usename = Column(String)
    passwd = Column(UnicodeText, primary_key=True)
    datecreated = Column(DateTime)


class PgAuthid(Base):  # pylint: disable=R0903, W0232
    """
    Class for pg_authid db table
    """
    __tablename__ = 'pg_authid'

    rolname = Column(String, primary_key=True)
    rolpassword = Column(UnicodeText)


class MSDBPwdSetter(object):  # pylint: disable=R0903
    """
    Class to update password of postgres db user on MS
    """

    def __init__(self):
        self.args = None
        self.user = 'postgres'
        self.passwd = None
        self.md5hash = None
        self.db_sessionmaker = sessionmaker()
        self.db_pg_sessionmaker = sessionmaker()

    def _get_passwd_hist(self, num_passwds):
        """
        Return the last n passwords in the password history table
        """
        with db_session_scope(self.db_sessionmaker) as db_session:
            passwd_hist = db_session.query(PgPasswdHist.passwd) \
                              .order_by(PgPasswdHist.datecreated.desc()) \
                              .limit(num_passwds)
            return [x.passwd for x in passwd_hist]

    def _get_current_password(self):
        """
        Select current password from the database
        """
        with db_session_scope(self.db_pg_sessionmaker) as db_session:
            auth_id = db_session.query(PgAuthid.rolpassword) \
                          .filter(PgAuthid.rolname == self.user).one()
            return auth_id.rolpassword

    def _password_applied_successfully(self):
        """
        Write password to password hist table on database and puppet manifest
        """
        try:
            with db_session_scope(self.db_sessionmaker) as db_session:
                self._update_password_hist(db_session)
                self._write_password_to_manifest()
                return True
        except IOError as exc:
            sys.stderr.write('Error writing to puppet manifest '
                             '{0}\n'.format(exc))

        return False

    def _update_password_hist(self, db_session):
        """
        Store new password in password history table and delete all except the
        last 5 records in password history table
        """
        pwd_hist = PgPasswdHist(usename=self.user,
                                passwd=unicode(self.md5hash, 'utf-8'),
                                datecreated=datetime.datetime.now())
        db_session.add(pwd_hist)

        passwd_hist = db_session.query(PgPasswdHist) \
                              .order_by(PgPasswdHist.datecreated.desc()) \
                              .slice(NUM_PREV_PASSWDS_DISALLOWED, None)
        for p_hist in passwd_hist:
            db_session.delete(p_hist)

    def _write_password_to_manifest(self):
        """
        Write password to puppet manifest
        """
        litp_root_dir = cherrypy.config.get('litp_root')
        pp_filepath = os.path.join(litp_root_dir, PP_MODULE_DIR, PP_FILE)

        try:
            with open(pp_filepath, 'w') as pp_file:
                pp_file.write(PP_FILE_TEMPLATE.format(self.md5hash))
                try:
                    os.fchown(pp_file.fileno(), -1,
                              grp.getgrnam(PUPPET_GROUP_NAME).gr_gid)
                except KeyError as exc:
                    sys.stderr.write('Warning: Could not change group name of '
                                     '{0}. Group {1} not found: {2}\n'.format(
                                     pp_filepath, PUPPET_GROUP_NAME, exc))
        except IOError as exc:
            raise

    def _md5_hash(self, passwd):
        """
        Return md5 hash of password and username
        """
        return 'md5' + hashlib.md5(passwd + self.user).hexdigest()

    def _validate_password(self):
        """
        Validate that password meets acceptance criteria
        Return error message, or None if password is valid
        """
        pwd_regex = r"^(?=[^A-Z]*[A-Z])(?=[^a-z]*[a-z])(?=\D*\d)[\w\-_.]{8,}$"
        if (not re.match(pwd_regex, self.passwd) or
            self.user.lower() in self.passwd.lower()):
            return ERR_PASSWORD_INVALID

        if self.md5hash in self._get_passwd_hist(NUM_PREV_PASSWDS_DISALLOWED):
            return ERR_PWD_REPEAT

        return None

    def _can_accept_new_password(self):
        """
        Prompt user for current passsword and validate that input password
        hash matches the value from the pg_authid table.
        Also check that there is no pending password update, that is puppet
        has not yet applied a previously input password.
        """
        current_pwd = self._get_current_password()
        if not current_pwd:
            return False

        pwd_hist = self._get_passwd_hist(1)
        if pwd_hist and pwd_hist[0] != current_pwd:
            sys.stderr.write('\n' + WARN_PWD_UPDATE_PENDING + '\n')
            return False

        try:
            for _ in xrange(MAX_PROMPT_TRIES):
                pwd = getpass.getpass('Current password: ')
                if self._md5_hash(pwd) == current_pwd:
                    return True
                sys.stdout.write(WARN_CURR_PWD_MISMATCH + '\n')
            return False
        except KeyboardInterrupt as exc:
            sys.stderr.write('\nError on input of password: {0}\n'.format(exc))
            return False

    @staticmethod
    def _get_new_password():
        """
        Prompt user to input password.
        Return new password input or None
        """
        try:
            for _ in xrange(MAX_PROMPT_TRIES):
                pw1 = getpass.getpass('New password: ')
                if pw1:
                    pw2 = getpass.getpass('Confirm new password: ')
                    if pw1 == pw2:
                        return pw1
                    sys.stdout.write(WARN_PWD_MISMATCH + '\n')
                else:
                    sys.stdout.write(WARN_EMPTY_PASSWORD + '\n')
            return None
        except KeyboardInterrupt as exc:
            sys.stderr.write('\nError on input of password: {0}\n'.format(exc))
            return None

    def _password_set(self):
        """
        Get current password and set new password
        """
        if not self._can_accept_new_password():
            return False

        self.passwd = self._get_new_password()
        if not self.passwd:
            return False

        self.md5hash = self._md5_hash(self.passwd)

        err = self._validate_password()
        if err:
            sys.stderr.write(ERR_PASSWORD_BAD.format(err=err))
            return False

        return self._password_applied_successfully()

    def _setup_db_sessions(self):
        """
        Create sqlalchemy engines and bind to sessionmakers
        """
        try:
            cherrypy.config.update(self.args.config_file)
            db_string = cherrypy.config.get('sqlalchemy.url')
            self.db_sessionmaker.configure(bind=create_engine(
                db_string.replace('\'', '')))
            db_string = cherrypy.config.get('sqlalchemy_pg.url')
            self.db_pg_sessionmaker.configure(bind=create_engine(
                db_string.replace('\'', '')))
        except SQLAlchemyError as exc:
            sys.stderr.write('Error connecting to postgres database: '
                             '{0}\n'.format(exc))
            return False

        return True

    def run(self, args):
        """
        Parse arguments, set up database connection and call method to set
        the password
        """
        if os.getuid():  # Not root
            sys.stdout.write('\nPermission denied\n')
            return 1

        parser = argparse.ArgumentParser(
            description="litpmsdbpwd command line interface to set password"
                        " for postgres user on MS."
        )
        parser.add_argument('-c', '--config-file', type=str,
                    default='/etc/litpd.conf',
                    help='Specify litp config file, default /etc/litpd.conf')
        self.args = parser.parse_args(args)

        if self._setup_db_sessions():
            if self._password_set():
                sys.stdout.write('\nPassword set\n')
                return 0

        return 1


if __name__ == '__main__':
    exit(MSDBPwdSetter().run(sys.argv[1:]))
