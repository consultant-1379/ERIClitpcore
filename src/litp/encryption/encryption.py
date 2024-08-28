##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

"""Module provides methods to encrypt and decrypt data for use with
sensitive information.  Only AES encryption is used here
encryption."""
#from Crypto import Random  # Not available in RHEL 6.4
from Crypto.Util.randpool import RandomPool
from Crypto.Cipher import AES
from base64 import standard_b64encode, standard_b64decode
from grp import getgrnam
from pwd import getpwnam
import os


class EncryptionAES(object):
    """AES Encryption class

    Encrypts 16 byte block base64 encoded data using AES-128-ECB """

    def generate_key(self):
        """Generate a new key which can encrypt and decrypt data
        :returns: Generated key.
        :rtype: str"""
        #key = Random.new().read(32)
        key = RandomPool().get_bytes(32)
        return key

    def check_key(self, location):
        """Check key exists at file location

        :param location: File location where key is saved.
        :type location: str
        :returns: True if key exists, false otherwise.
        :rtype: bool"""
        return os.path.exists(location)

    def write_key(self, location, key):
        """Save a private RSA key to the location

        :param location: File location to save key.
        :type location: str
        :param key: RSA key to save.
        :type key: str
        :raises IOError: If IO is interrupted while writing file."""
        with open(location, 'w') as f:
            f.write(standard_b64encode(key))
        try:
            os.chmod(location, 0440)
            os.chown(location, getpwnam("root").pw_uid,
                     getgrnam("litp-admin").gr_gid)
        except OSError as e:
            print "Permission denied."
        except KeyError:
            print "Group litp-admin does not exist."

    def read_key(self, location):
        """Read a private RSA key from the location

        :param location: File location where is key is saved.
        :type location: str
        :returns: RSA key from file.
        :rtype: str
        :raises IOError: If IO is interrupted while reading file."""

        with open(location, 'r') as f:
            key = standard_b64decode(f.readlines()[0])

        return key

    def encrypt(self, key, data=''):
        """Encrypt data and then base-64 encode it

        :param key: RSA key to encrypt with
        :type key: str
        :param data: data to encrypt
        :type data: str
        :returns: Encoded data
        :rtype: str
        :raises ValueError: If key is not valid string.
        :raises TypeError: If data is not valid string"""
        # Create encryptor from AES module
        encryptor = AES.new(key, AES.MODE_CFB, '0' * AES.block_size,
                            segment_size=128)

        return standard_b64encode(encryptor.encrypt(self._pad(data)))

    def decrypt(self, key, data=''):
        """Decrypt data and then base-64 decode it

        :param key: RSA key to decrypt with
        :type key: str
        :param data: data to decrypt
        :type data: str
        :raises TypeError: If key or data is not valid string"""

        if not data:
            return ''  # Should raise TypeError: Not encrypted value
        # Create encryptor from AES module
        decryptor = AES.new(key, AES.MODE_CFB, '0' * AES.block_size,
                            segment_size=128)

        return decryptor.decrypt(standard_b64decode(data)).rstrip(chr(3))

    @staticmethod
    def _pad(data, padding=16):
        """Pads data with EXT [chr(3)] to ensure length is multiple
           of 16 similar to PKCS7 RFC 5652"""
        p = (padding - (len(data) - 1) % padding) - 1
        return data + chr(3) * p
