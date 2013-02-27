## FileStruct

FileStruct (https://github.com/appcove/FileStruct) is a general purpose file server and file cache for web application servers.

The primary goal is to create a high-performance and sensible local file server for web applications.  The secondary goal is to enable FileStruct to be a caching layer between an application and a storage backend (like Amazon S3).

## Setup Instructions

#### Create your database directory
```bash
$ mkdir /path/to/database
$ chmod 770 /path/to/database
```
Note that the database MUST have group write permissions. 

#### Verify the group is correct
The group of `/path/to/database` will be used throughout the entire database directory.  Any user who wishes to write to the database must be in this group.  Permissions are checked on startup, so if the user is not a member of this group, then a `ConfigError` will be raised.

#### Create a `FileStruct.json`
```bash
$ echo '{"Version":1}' > /path/to/database/FileStruct.json
```

Why do we require this file?  It is a safe-guard against writing into a directory accidentally.  If this file does not exist, then the database client will raise a `ConfigError`.

If you are running code under **apache**, it will by default run as the `apache` user.  You may need to add a group to the `apache` user in order to have it access the database.  Assuming the database is owned by the `fileserver` group, then:

```bash
# usermod -a -G fileserver apache
```

may be used to add `apache` to the `fileserver` group.

#### Connect the client
```python
>>> import FileStruct
>>> client = FileStruct.Client('/path/to/database')
>>> client.PutData(b'test')
'a94a8fe5ccb19ba61c4c0873d391e987982fbbd3'
>>> client['a94a8fe5ccb19ba61c4c0873d391e987982fbbd3'].GetData()
b'test'
```

Assuming you are user `jason` and you created the `/path/to/database` to have the group `fileserver`, then the above will result in:

```text
$ ls -al /path/to/database
drwxrwxr-x. 2 jason      fileserver 4096 Feb 22 17:13 Data
drwxrwxr-x. 2 jason      fileserver 4096 Feb 22 17:13 Error
-rw-r--r--. 1 fileserver fileserver   88 Feb 22 16:55 FileStruct.json
drwxrwxr-x. 2 jason      fileserver 4096 Feb 22 17:13 Temp
drwxrwxr-x. 2 jason      fileserver 4096 Feb 22 17:13 Trash
```

You are now ready to use FileStruct!

## Design Goals

### Immutable Files
FileStruct is designed to work with files represented by the SHA-1 hash of their contents. This means that all files in FileStruct are immutable.

### High Performance
FileStruct is designed as a local repository of file data accessable (read/write) by an application or web application.  All operations are local I/O operations and therefore, very fast.

Where possible, streaming hash functions are used to prevent iterating over a file twice.

### Direct serving from Nginx
FileStruct is designed so that Nginx can serve files directly from it's Data directory using an `X-Accel-Redirect` header.  For more information on this Nginx configuration directive, see http://wiki.nginx.org/XSendfile

Assuming that ***nginx*** runs under `nginx` user and file database is owned by the `fileserver` group, `nginx` needs to be in the `fileserver` group to serve files:
```bash
# usermod -a -G fileserver nginx
```

### Secure
FileStruct is designed to be as secure as your hosting configuration.  Where possible, a dedicated user should be allocated to read/write to FileStruct, and the database directory restricted to this user.

### Simple
FileStruct is designed to be incredibly simple to use.

### File Manipulaion
FileStruct is designed to simplify common operations on files, especially uploaded files.  Image resizing for thumbnails is supported.

### Temporary File Management
FileStruct is designed to simplify the use of Temp Files in an application.  The API supports creation of a temporary directory, placing files in it, Ingesting files into FileStruct, and deleting the directory when completed (or retaining it in the event of an error)

### Garbage Collection
FileStruct is designed to retain files until garbage collection is performed.  Garbage collection consists of telling FileStruct what files you are interested in keeping, and having it move the remaining files to the trash.

### Backup and Sync with Rsync
FileStruct is designed to work seamlessly with rsync for backups and restores.

### Atomic operations
At the point a file is inserted or removed from FileStruct, it is a filesystem move operation.  This means that under no circumstances will a file exist in FileStruct that has contents that do not match the name of the file.

### No MetaData
FileStruct is not designed to store MetaData.  It is designed to store file content. There may be several "files" which refer to the same content.  `empty.log`, `empty.txt`, and `empty.ini` may all refer to the empty file `Data/da/39/da39a3ee5e6b4b0d3255bfef95601890afd80709`.  However, this file will be retained as long as any aspect of the application still uses it.

### Automatic De-Duplication
Because file content is stored in files with the hash of the content, automatic file-level de-duplication occurs. When a file is pushed to FileStruct that already exists, there is no need to write it again.  

This carries the distinct benifit of being able to use the same FileStruct database across multiple projects if desired, because the content of file `Data/da/39/da39a3ee5e6b4b0d3255bfef95601890afd80709` is always the same, regardless of the application that placed it there.

_**Note:** In the event that multiple instances or applications use the same database, the garbage collection routine MUST take all references to a given hash into account, across all applications that use the database.  Otherwise, it would be easy to delete data that should be retained._


## Database Design

The database should be placed in a secure directory that only the owner of the application can read and write to.  

**SECURITY NOTE:** _mod_wsgi runs by default as the apache user.  It can be configured to run as a different user.  We recommend a dedicated user to run the application and access FileStruct files._

```text
/path/to/app/database
  FileStruct.json
    contains a JSON value like {"Version": 1, "User": "MyApp", "Group": "MyApp"}

  Data
    {00-ff}
      {00-ff}
        [0-9a-f]{40}
    da
      39
        da39a3ee5e6b4b0d3255bfef95601890afd80709
        da3968daecd823babbb58edb1c8e14d7106e83bb
    ...

  Error
    20130220151717-86718750-24386270
      Python-Exception.txt
      file1.whatever
      yourfile.txt
    ...

  Temp
    20130220151713-62109375-21427441
      upload.jpg
      resize.jpg
    ...

  Trash
    20130220164717-46718750-24343534
      da39a3ee5e6b4b0d3255bfef95601890afd80709
      77de68daecd823babbb58edb1c8e14d7106e83bb
      f1f836cb4ea6efb2a0b1b99f41ad8b103eff4b59
      35139ef894b28b73bea022755166a23933c7d9cb
    ...

```

In order for the FileStruct Client to operate, the FileStruct.json file must be present and readable.  If any of the above top-level directories are missing, they will be automatically created by FileStruct.  

Each file placed in the `database/Data` directory will have write permissions removed.  This is to hopefully prevent accidental modification of immutable data in the database.

## Configuration: `FileStruct.json`

Each time a `FileStruct.Client` object is created, the `FileStruct.json` file is loaded.  The contents of this file are a simple JSON string.  

**Note: Lines beginning with # are ignored.**

```json
{
  "Version": 1,
  "User": "MyApp",
  "Group": "MyApp"
}
```

#### `Version`
For future adjustments to the database format.  Currently must be `1`.

#### `User`
The user that "owns" the database.  Can be an integer UID or string Username.  
`"User": 500` and `"User": "MyApp"` are both valid.

#### `Group`
The primary group that "owns" the database.  Can be an integer UID or string Username.  
`"User": 500` and `"User": "MyApp"` are both valid.


## `FileStruct.Client(Path, NginxLocation)`

Import `FileStruct` and create an instance of the `Client` class.  This operation will open `FileStruct.json`, verify it's contents, and check for the existence of several directories.  Therefore it is best to create a aingle instance and re-use it.

**`FileStruct.Client` instances methods are THREAD SAFE.**

```python
import FileStruct

client = FileStruct.Client(
  Path = '/home/myapp/filestruct',
  NginxLocation = '/FileStruct',
  )
```

### `hash in client`
Returns True if the specified hash exists in the database.  Otherwise returns False.  Improperly formed hashes do not raise an error in this method.

### `client[hash]`
Returns a `FileStruct.HashFile` object or raises a `KeyError`.  See **Working with Files** for more information.

### `client.Path`
Fully qualified filesystem path to the database.

### `client.bin_convert`
Full path to ImageMagick convert binary.  Defaults to `/usr/bin/convert`.

### `client.TempDir()`

Return a `FileStruct.TempDir` object (context manager) which will create a temporary directory and (typically) remove it when finished.  See **Working with Files** for more information.

```python
with client.TempDir() as TempDir:
   open(TempDir['data.dat'].Path, 'wb').write(mydata)
   hash = TempDir['data.dat'].Save()
```

### `client.PutStream(stream)`
Reads all data from `stream`, which must be an object with a `.read()` interface, returning bytes.  Does not attempt to rewind first, so make sure the stream is "ready to read".  Places the file in the database and returns the hash.

### `client.PutData(data)`
Takes a `bytes` object and saves it to the database.  Returns the hash.

### `client.PutFile(path)`
Takes the path to a file.  Reads the file into the database.  Does not modify the original file.  Returns the hash.




## Working with Files

### `hash in client`
Returns True if the specified hash exists in the database.  Otherwise returns False.  Improperly formed hashes do not raise an error in this method.

_Future Note: in the event that FileStruct has a remote back-end, like Amazon S3, this could be a resource-intensive operation._

### `client[hash]`
Returns a `FileStruct.HashFile` object which wraps a file in the database.  If the file does not exist, a `KeyError` is raised.

#### `client[hash].Path`
Returns the full path to this temporary file (regardless of existence)

#### `client[hash].Hash`
The 40 character hash.

#### `client[hash].Path`
The full filesystem path to the hash file in the database.  This is for **READ ONLY** purposes.  Because the process calling this code has authority to write to this file, the database could be corrupted if this path is written to in any way.

#### `client[hash].GetStream()`
Opens the hash file in the database for reading (bytes).  Because this is a pass through to `open()`, it can be used as a context manager (`with` statement).

#### `client[hash].GetData()`
Reads the entire file into memory as a `bytes` object  
**Warning: do not use this with large files.**

#### `client[hash].InternalURI`
Returns an internal URI suitable for passing back to a front-end webserver, such as nginx.  Joins the `client.InternalLocation` with the rest of the `database/Data/...` path to produce a URL that can be used with `X-Accel-Redirect`.

```python
headers.add_header('Content-type', 'image/jpeg')
headers.add_header('X-Accel-Redirect', client[hash].InternalURI)
```

Example nginx configuration snippet:
```conf
location ^~ /FileStruct/
{
    internal;
    alias /path/to/my/database/Data/;  #TRAILING SLASH IMPORTANT
}
```

Example return: 
```python
>>> client = FileServer.Client(Path, InternalLocation='/FileStruct')
>>> client['da39a3ee5e6b4b0d3255bfef95601890afd80709'].InternalURI
'/FileStruct/da/39/da39a3ee5e6b4b0d3255bfef95601890afd80709'
```

More info on XSendFile here: http://wiki.nginx.org/XSendfile

### `client.TempDir()`

Return a context manager which will create a temporary directory and (typically) remove it when the context manager exits.  For example:

```python
with client.TempDir() as TempDir:
   open(TempDir.FilePath('upload.jpg'), 'wb').write(mydata)
   TempDir.ResizeImage('upload.jpg', 'resize.jpg', '100x100')
   hash1 = TempDir.Save('upload.jpg')
   hash2 = TempDir.Save('resize.jpg')
```

When the context manager is entered, the directory is:

1. Created in `database/Temp/...`
2. The directory is named `YYYYMMDDhhmmss.fraction.randomnn`
3. For example: `database/Temp/20130220154544-39453125-17036182`

When the context manager is exited, the directory is:

1. Removed (default action)
2. Moved to database/Error (in the event `TempDir.Retain == True`)
3. Moved to `database/Error` with `Python-Exception.txt` written (in the event of an exception)

#### `TempDir.Client`
A reference to the `FileStruct.Client` object that created this `FileStruct.TempDir` object.

#### `TempDir.Path`
The full path of the temporary directory.

#### `TempDir.Retain`
Defaults to `False`.  Set to `True` to cause the temporary directory to be moved to the `database/Error` directory when the context manager exits (e.g. end of `with` statement).  

#### `TempDir[filename]`
Returns a TempFile object with the name specified in `filename`.  

`filename` is restricted to the following: `[a-zA-Z0-9_.+-]{1,255}`

#### `TempDir[filename].Link(hash)`
Create a symbolic link in the temporary directory to the specified hash file in the database.  This is useful for obtaining access to files for subsequent operations, like an image resize.

#### `TempDir[filename].GetStream()`
Opens the temporary file for reading (bytes).  Because this is a pass through to `open()`, it can be used as a context manager (`with` statement).

#### `TempDir[filename].GetData()`
Reads the entire temporary file into memory as a `bytes` object  
**Warning: do not use this with large files.**

#### `TempDir[filename].PutStream(stream)`
Opens `filename` in the temporary directory for writing, and writes the entire contents of `stream` to it.

#### `TempDir[filename].PutData(data)`
Opens `filename` in the temporary directory for writing and writes the entire contents of `data` to it.  `data` must be `bytes`.

#### `TempDir[filename].PutFile(file)`
Opens `filename` in the temporary directory for writing and writes the entire contents of `file` to it. 

#### `TempDir[filename].Ingest()`
Calculates the hash of this file and then moves it into the database.  Returns the 40 character hash.  This **moves** the file, so it will no longer exist in the temporary directory.


------
vim:encoding=utf-8:ts=2:sw=2:expandtab 
