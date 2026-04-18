# mhlver

`mhlver` is a streamlined CLI utility to find and verify Media Hash List files (MHL). It provides unified support for both traditional MHL and ASC-MHL 2.0, and it features a compliance validator for XML Schema Definition (XSD) on legacy workflows.

#### 💻 Compatibility

* macOS
* Linux

#### 🛠️ Dependencies

`mhlver` utilizes the following open-source components:
* [Python](https://docs.python.org/3/license.html) 3.9+ © 2001-2026 Python Software Foundation (PSF)
* [python-xxhash](https://github.com/ifduyue/python-xxhash) © 2014-2026 Yue Du (BSD-2-Clause)
* [lxml](https://lxml.de/) © 2004-2026 Stefan Behnel, et al. (BSD-3-Clause)
* [ASC-MHL](https://pypi.org/project/ascmhl/) 1.2 © 2022-2026 Academy of Motion Picture Arts and Sciences (MIT)

#### 🚀 Installation

1. Install [Homebrew](https://brew.sh/) (if not already installed):
```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

2. Tap and install:
```
brew tap lucuma13/dit
brew install mhlver
```

#### 📖 Usage

`mhlver [options] <path>`

| Option | Description |
| :---: | :--- |
| `-d`, `--datestamp` | Prepend a datestamp for reporting |
| `-s`, `--schema` | Validate XML Schema Definition (MHL v1 only) |
| `-v`, `--verbose` | Verbose |
| `-h`, `--help` | Show help message |
| `--version` | Print version |

Note: `<path>` can be a single file or a directory, or the current directory if left blank.
