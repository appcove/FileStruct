## FileStruct

FileStruct (https://github.com/appcove/FileStruct) is a general purpose file server and file cache for web application servers.

The primary goal is to create a high-performance and sensible local file server for web applications.  The secondary goal is to enable FileStruct to be a caching layer between an application and a storage backend (like Amazon S3).


## Design Goals

### Immutable Files
FileStruct is designed to work with files represented by the SHA-1 hash of their contents. This means that all files in FileStruct are immutable.

### High Performance
FileStruct is designed as a local repository of file data accessable (read/write) by an application or web application.  All operations are local I/O operations and therefore, very fast.

Where possible, streaming hash functions are used to prevent iterating over a file twice.

### Direct serving from Nginx
FileStruct is designed so that Nginx can serve files directly from it's Data directory using an `X-Accel-Redirect` header.  For more information on this Nginx configuration directive, see http://wiki.nginx.org/XSendfile

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
Because file content is stored in files with the hash of the content, automatic file-level de-duplication occurs. When a file is pushed to FileStruct that already exists, there is no need to write it again.  This carries the distinct benifit of being able to use the same FileStruct database across multiple projects if desired, because the content of file `Data/da/39/da39a3ee5e6b4b0d3255bfef95601890afd80709` is always the same, regardless of the application that placed it there.

## Database Design

The database should be placed in a secure directory that only the owner of the application can read and write to.  

**SECURITY NOTE:** _mod_wsgi runs by default as the apache user.  It can be configured to run as a different user.  We recommend a dedicated user to run the application and access FileStruct files._

```text
/path/to/app/database
  FileStruct.json
    contains a JSON value like {"Version": 1}

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
  NginxPrefix = '/FileStruct',
  )
```

### `hash in client`
Returns True if the specified hash exists in the database.  Otherwise returns False.  Improperly formed hashes do not raise an error in this method.

### `client[hash]`
Returns a `FileStruct.HashFile` object or raises a `KeyError`.  See **Working with Files** for more information.

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

### `client[hash]`
Returns a `FileStruct.HashFile` object which wraps a file in the database.  If the file does not exist, a `KeyError` is raised.

#### `client[hash].Path`
Returns the full path to this temporary file (regardless of existence)

#### `client[hash].Hash`
The 40 character hash.

#### `client[hash].Path`
The full filesystem path to the hash file in the database.  This is for **READ ONLY** purposes.  Because the process calling this code has authority to write to this file, the database could be corrupted if this path is written to in any way.

#### `client[hash].Stream()`
Opens the hash file in the database for reading

#### `client[hash].NginxHeaders()`
Returns a list of 2-tuples to be set as Nginx headers.  For example:

```python
[
  ('X-Accel-Redirect', '/FileStruct/da/39/da39a3ee5e6b4b0d3255bfef95601890afd80709),
]
```

Note: this is formed as a list to allow for future addition of other headers that may be useful to Nginx.


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

#### `TempDir[filename].Ingest()`
Calculates the hash of this file and then moves it into the database.  Returns the 40 character hash.

#### `TempDir[filename].PutStream(stream)`
Opens `filename` in the temporary directory for writing, and writes the entire contents of `stream` to it.

#### `TempDir[filename].PutData(data)`
Opens `filename` in the temporary directory for writing and writes the entire contents of `data` to it.  `data` must be `bytes`.

#### `TempDir[filename].PutFile(file)`
Opens `filename` in the temporary directory for writing and writes the entire contents of `file` to it. 



------
vim:encoding=utf-8:ts=2:sw=2:expandtab 
