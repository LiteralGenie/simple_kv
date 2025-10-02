# Setup

```bash
# Create / delete user
python3 -m simple_kv.admin create USERNAME PASSWORD
python3 -m simple_kv.admin delete USERNAME PASSWORD

# Mark user as admin (can access all tables)
python3 -m simple_kv.admin admin USERNAME

# Enable read / write access for specific tables
python3 -m simple_kv.admin table USERNAME TABLE_1 TABLE_2 ...
python3 -m simple_kv.admin table USERNAME --no-read TABLE_1 TABLE_2 ...
python3 -m simple_kv.admin table USERNAME --no-write TABLE_1 TABLE_2 ...

# Most commands have a --remove option to invert the operation
# (eg delete a user instead of creating one, remove a permission instead of adding it, etc)
```

# Usage

```bash
# Request session id
curl 'http://localhost:8267/login' \
-X POST \
--data '{ "username": "...", "password": "..." }'
# {"sid":"some_session_id","uid":2,"duration":86400}

# Create table
curl 'http://localhost:8267/create_kv' \
-X POST \
--data '{ "name": "test", "allow_guest_read": true, "allow_guest_write": false }' \
-H 'Cookie: sid=some_session_id'

# Insert key-value data
curl 'http://localhost:8267/kv/test/my_key' \
-X POST \
--data '{ "value": "my_value" }' \
-H 'Cookie: sid=some_session_id'

# Read data
curl 'http://localhost:8267/kv/test/my_key'
# {"value":"my_value","exists":true}
```
