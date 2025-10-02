```bash
# Create / delete user
python3 -m simple_kv.admin register USERNAME PASSWORD

# Mark user as admin (can access all tables)
python3 -m simple_kv.admin admin USERNAME

# Enable read / write access for specific tables
python3 -m simple_kv.admin table USERNAME TABLE_1 TABLE_2 ...
python3 -m simple_kv.admin table USERNAME --no-read TABLE_1 TABLE_2 ...
python3 -m simple_kv.admin table USERNAME --no-write TABLE_1 TABLE_2 ...

# Most commands have a --remove option to invert the operation
# (eg delete a user instead of creating one, remove a permission instead of adding it, etc)
```
