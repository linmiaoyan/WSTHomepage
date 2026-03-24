# QuickForm SQL 文件导入说明

本目录提供了三种方式将 `quickform_backup.sql` 文件导入到 MySQL 数据库的 `quickform` 表中。

## 方法一：使用 Python 脚本（推荐）

### 1. 安装依赖

```bash
pip install pymysql
```

### 2. 运行脚本

```bash
python import_quickform_sql.py
```

或者直接指定 SQL 文件路径：

```bash
python import_quickform_sql.py "D:\path\to\quickform_backup.sql"
```

### 3. 按提示输入数据库信息

- 主机地址（默认：localhost）
- 端口（默认：3306）
- 用户名（默认：root）
- 密码
- 数据库名（默认：quickform）

## 方法二：使用批处理脚本（Windows）

### 1. 编辑 `import_quickform_sql.bat`

打开文件，修改以下变量：

```batch
set MYSQL_HOST=localhost
set MYSQL_PORT=3306
set MYSQL_USER=root
set MYSQL_PASSWORD=your_password  # 修改为你的密码
set MYSQL_DATABASE=quickform
set SQL_FILE=quickform_backup.sql  # 如果文件不在当前目录，请使用完整路径
```

### 2. 运行脚本

双击 `import_quickform_sql.bat` 或在命令行中运行：

```cmd
import_quickform_sql.bat
```

## 方法三：使用 Shell 脚本（Linux/Mac）

### 1. 编辑 `import_quickform_sql.sh`

打开文件，修改以下变量：

```bash
MYSQL_HOST="localhost"
MYSQL_PORT="3306"
MYSQL_USER="root"
MYSQL_PASSWORD="your_password"  # 修改为你的密码
MYSQL_DATABASE="quickform"
SQL_FILE="quickform_backup.sql"  # 如果文件不在当前目录，请使用完整路径
```

### 2. 添加执行权限并运行

```bash
chmod +x import_quickform_sql.sh
./import_quickform_sql.sh
```

## 方法四：直接使用 MySQL 命令行

### Windows (PowerShell/CMD)

```bash
mysql -h localhost -P 3306 -u root -p quickform < quickform_backup.sql
```

### Linux/Mac

```bash
mysql -h localhost -P 3306 -u root -p quickform < quickform_backup.sql
```

系统会提示输入密码。

## 注意事项

1. **确保数据库存在**：在导入之前，请确保 `quickform` 数据库已经创建：

   ```sql
   CREATE DATABASE IF NOT EXISTS quickform CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

2. **备份现有数据**：如果数据库中已有数据，建议先备份：

   ```bash
   mysqldump -u root -p quickform > quickform_backup_before_import.sql
   ```

3. **字符编码**：确保 SQL 文件使用 UTF-8 编码，以避免中文乱码问题。

4. **文件路径**：如果 SQL 文件不在当前目录，请使用完整路径。

5. **权限问题**：确保 MySQL 用户有足够的权限执行 SQL 语句。

## 常见问题

### Q: 导入时出现 "Access denied" 错误
A: 检查用户名和密码是否正确，以及该用户是否有访问数据库的权限。

### Q: 导入时出现 "Unknown database" 错误
A: 先创建数据库：`CREATE DATABASE quickform;`

### Q: 导入时出现中文乱码
A: 确保数据库和表的字符集为 `utf8mb4`，SQL 文件也使用 UTF-8 编码。

### Q: 导入时出现 "Table already exists" 错误
A: 如果表已存在，SQL 文件中的 `CREATE TABLE` 语句会失败。可以：
- 先删除现有表：`DROP TABLE IF EXISTS table_name;`
- 或者修改 SQL 文件，使用 `CREATE TABLE IF NOT EXISTS`

## 验证导入结果

导入完成后，可以连接数据库验证：

```sql
USE quickform;
SHOW TABLES;
SELECT COUNT(*) FROM your_table_name;
```
