##
# Copyright (C) 2012 by Konstantin Ryabitsev and contributors
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA
# 02111-1307, USA.
#
import logging
import totpcgi

import exceptions

logger = logging.getLogger('totpcgi')

class BackendNotSupported(exceptions.Exception):
    def __init__(self, message):
        exceptions.Exception.__init__(self, message)
        logger.debug('!BackendNotSupported: %s' % message)

class Backends:
    
    def __init__(self):
        self.secret_backend  = None
        self.pincode_backend = None
        self.state_backend   = None

    def load_from_config(self, config):
        secret_backend_engine = config.get('secret_backend', 'engine')

        if secret_backend_engine == 'file':
            import totpcgi.backends.file
            secrets_dir = config.get('secret_backend', 'secrets_dir')
            self.secret_backend = totpcgi.backends.file.GASecretBackend(secrets_dir)

        elif secret_backend_engine == 'pgsql':
            import totpcgi.backends.pgsql
            pg_connect_string = config.get('secret_backend', 'pg_connect_string')
            self.secret_backend = totpcgi.backends.pgsql.GASecretBackend(pg_connect_string)

        else:
            raise BackendNotSupported(
                    'secret_backend engine not supported: %s' % secret_backend_engine)

        pincode_backend_engine = config.get('pincode_backend', 'engine')

        if pincode_backend_engine == 'file':
            import totpcgi.backends.file
            pincode_file = config.get('pincode_backend', 'pincode_file')
            self.pincode_backend = totpcgi.backends.file.GAPincodeBackend(pincode_file)

        elif pincode_backend_engine == 'pgsql':
            import totpcgi.backends.pgsql
            pg_connect_string = config.get('pincode_backend', 'pg_connect_string')
            self.pincode_backend = totpcgi.backends.pgsql.GAPincodeBackend(pg_connect_string)

        elif pincode_backend_engine == 'ldap':
            import totpcgi.backends.ldap
            ldap_url    = config.get('pincode_backend', 'ldap_url')
            ldap_dn     = config.get('pincode_backend', 'ldap_dn')
            ldap_cacert = config.get('pincode_backend', 'ldap_cacert')

            self.pincode_backend = totpcgi.backends.ldap.GAPincodeBackend(ldap_url, ldap_dn, ldap_cacert)
        else:
            raise BackendNotSupported(
                    'pincode_engine not supported: %s' % pincode_backend_engine)


        state_backend_engine = config.get('state_backend', 'engine')

        if state_backend_engine == 'file':
            import totpcgi.backends.file
            state_dir = config.get('state_backend', 'state_dir')
            self.state_backend = totpcgi.backends.file.GAStateBackend(state_dir)

        elif state_backend_engine == 'pgsql':
            import totpcgi.backends.pgsql
            pg_connect_string = config.get('state_backend', 'pg_connect_string')
            self.state_backend = totpcgi.backends.pgsql.GAStateBackend(pg_connect_string)

        else:
            syslog.syslog(syslog.LOG_CRIT, 
                    'state_backend engine not supported: %s' % state_backend_engine)

############################### API STUBS #################################

class GAStateBackend:
    def __init__(self):
        pass

    def get_user_state(self, user):
        pass

    def update_user_state(self, user, state):
        pass

    def _remove_user_state(self, user):
        pass

class GASecretBackend:
    def __init__(self):
        pass

    def get_user_secret(self, user, pincode=None):
        pass

    def _decrypt_secret(self, secret, pincode):
        import base64
        import hashlib
        import hmac
        from Crypto.Cipher import AES
        from passlib.utils.pbkdf2 import pbkdf2

        AES_BLOCK_SIZE = 16
        KDF_ITER       = 2000
        SALT_SIZE      = 16
        KEY_SIZE       = 32

        # split the secret into components
        try:
            (scheme, salt, ciphertext) = secret.split('$')
            salt       = base64.b64decode(salt)
            ciphertext = base64.b64decode(ciphertext)
        except (ValueError, TypeError):
            raise totpcgi.UserSecretError('Failed to parse encrypted secret')

        aes_salt  = salt[:SALT_SIZE]
        hmac_salt = salt[SALT_SIZE:]

        sig_size = hashlib.sha256().digest_size
        sig      = ciphertext[-sig_size:]
        data     = ciphertext[:-sig_size]

        # verify hmac sig first
        hmac_key = pbkdf2(pincode, hmac_salt, KDF_ITER, KEY_SIZE, 
                          prf='hmac-sha256')

        if hmac.new(hmac_key, data, hashlib.sha256).digest() != sig:
            raise totpcgi.UserSecretError('Failed to verify hmac!')

        aes_key = pbkdf2(pincode, aes_salt, KDF_ITER, KEY_SIZE, 
                         prf='hmac-sha256')

        iv_bytes = data[:AES_BLOCK_SIZE]
        data     = data[AES_BLOCK_SIZE:]

        cypher = AES.new(aes_key, AES.MODE_CBC, iv_bytes)
        data   = cypher.decrypt(data)
        secret = data[:-ord(data[-1])]

        logger.debug('Decryption successful')

        return secret

class GAPincodeBackend:
    def __init__(self):
        pass

    def verify_user_pincode(self, user, pincode):
        pass

    def _verify_by_hashcode(self, pincode, hashcode):
        try:
            (junk, algo, salt, junk) = hashcode.split('$', 3)
        except ValueError:
            raise totpcgi.UserPincodeError('Unsupported hashcode format')

        if algo not in ('1', '5', '6', '2a', '2x', '2y'):
            raise totpcgi.UserPincodeError('Unsupported hashcode format: %s' % algo)

        if algo in ('2a', '2x', '2y'):
            logger.debug('$%s$ found, will use bcrypt' % algo)

            import bcrypt
            if bcrypt.hashpw(pincode, hashcode) != hashcode:
                raise totpcgi.UserPincodeError('Pincode did not match.')
        else:
            logger.debug('$%s$ found, will use crypt' % algo)

            import crypt
            salt_str = '$%s$%s' % (algo, salt)
            if crypt.crypt(pincode, salt_str) != hashcode:
                raise totpcgi.UserPincodeError('Pincode did not match.')

        return True
