```sql
INSERT INTO users (user, pass) VALUES ('ADMIN_USER', 'ADMIN_PASS');
INSERT INTO users_permissions (uid, perm) SELECT id as uid, 'admin' as perm FROM users WHERE user = 'ADMIN_USER';
```
