"""
Created on Nov 13, 2013.

@author: marco

"""
import os
import unittest
from base64 import standard_b64encode
from litp.encryption.encryption import EncryptionAES


class Test(unittest.TestCase):

    def setUp(self):
        self.location = "./unittestAES.key"

    def tearDown(self):
        for filename in ("./unittestRSA.key", "./unittestAES.key",
                         "./fail.arf"):
            try:
                os.remove(filename)
            except:
                pass

    def test_pad(self):
        message = "test_message"
        result = EncryptionAES._pad(message)
        self.assertEquals(message + chr(3) * 4, result)

        message = " message 16 long"
        result = EncryptionAES._pad(message)
        self.assertEquals(message, result)

        # Test messages of various lengths
        for i in range(32):
            result = EncryptionAES._pad("a" * i)
            self.assertEquals(len(result) % 16, 0)

    def test_generate(self):
        aes = EncryptionAES()
        # Test for 10 key generations rather than one.
        # All should be unique.
        keys = []
        for i in range(10):
            key = aes.generate_key()
            keys.append(key)

        # Passing list into set will remove duplicates,
        # if lengths are unequal duplicate has been created.
        self.assertEqual(len(keys), len(set(keys)))

    def test_encrypt_and_decrypt(self):
        aes = EncryptionAES()
        key = aes.generate_key()

        result = aes.encrypt(key, "Peter")

        # This verifies that data can be decrypted in one line
        self.assertEqual("Peter", aes.decrypt(key, result))
        # This is an example of bogus data

    def test_invalid_key_encrypt(self):
        aes = EncryptionAES()

        self.assertRaises(ValueError, aes.encrypt, '', '')

    def test_invalid_key_decrypt(self):
        aes = EncryptionAES()
        key = aes.generate_key()

        data = aes.encrypt(key, "aaaa")
        self.assertRaises(ValueError, aes.decrypt, '', data)

    def test_invalid_data_decrypt(self):
        aes = EncryptionAES()
        key = aes.generate_key()

        self.assertRaises(TypeError, aes.decrypt, key, "yoe")
        #self.assertRaises(TypeError, aes.decrypt, key, None)

    def test_decrypt_empty_data(self):
        aes = EncryptionAES()
        key = aes.generate_key()

        result = aes.decrypt(key, "")

        self.assertEquals(result, "")

    def test_write_key(self):
        aes = EncryptionAES()

        key = aes.generate_key()
        aes.write_key(self.location, key)
        with open(self.location, 'r') as f:
            data = f.readlines()
            self.assertEqual(standard_b64encode(str(key)),
                             data[0].rstrip())

    def test_read_key(self):
        aes = EncryptionAES()

        key = aes.generate_key()
        aes.write_key(self.location, key)

        # Test this static method
        key = aes.read_key(self.location)
        with open(self.location, 'r') as f:
            data = f.readlines()
            self.assertEqual(standard_b64encode(str(key)),
                             data[0].rstrip())

    def test_check_key_does_not_exist(self):
        aes = EncryptionAES()
        self.assertFalse(aes.check_key(self.location))

    def test_check_key_does_exist(self):
        aes = EncryptionAES()
        key = aes.generate_key()
        aes.write_key(self.location, key)

        self.assertTrue(aes.check_key(self.location))
