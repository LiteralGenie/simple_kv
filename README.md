# Here be dragons

This basically exposes an SQLite database to the internet. There is a permission / auth system and queries are [limited](https://github.com/LiteralGenie/simple_kv/blob/6be4a255ca56b414abf360709087fe028cbc6b73/simple_kv/lib/kv/kv_db.py#L57) in what functions / tables they can access but this is still largely untested.

Use at your own risk!

# Setup

```bash
# Download and install
git clone https://github.com/LiteralGenie/simple_kv
cd simple_kv
python3 -m venv venv
. ./venv/bin/activate
python -m pip install -e .

# Launch web server
python -m simple_kv.web

# Create / delete user
python -m simple_kv.admin create USERNAME PASSWORD
python -m simple_kv.admin delete USERNAME PASSWORD

# Mark user as admin (can access all tables)
python -m simple_kv.admin admin USERNAME

# Enable read / write access for specific tables
python -m simple_kv.admin table USERNAME TABLE_1 TABLE_2 ...
python -m simple_kv.admin table USERNAME --no-read TABLE_1 TABLE_2 ...
python -m simple_kv.admin table USERNAME --no-write TABLE_1 TABLE_2 ...

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
# Cookie header like above is required if table was created without allow_guest_read
curl 'http://localhost:8267/kv/test/my_key'
# {"value":"my_value","exists":true}
```
