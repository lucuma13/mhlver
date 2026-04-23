#!/usr/bin/env python3
# simple-mhl - Modern verification and sealing tool for legacy MHL files

import argparse
import getpass
import hashlib
import importlib.resources
import os
import platform
import sys
from datetime import datetime, timezone

import xxhash
from lxml import etree

VERSION = "1.0.0"

# Import XSD
def get_xsd_path():
    try:
        with importlib.resources.path("mhl_suite.xsd", "MediaHashList_v1_1.xsd") as p:
            return str(p)
    except (ImportError, FileNotFoundError, TypeError):
        pass

    # Fallback for local execution (remove before pushing code)
    local_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "xsd", "MediaHashList_v1_1.xsd"),
        "/Users/tash/Documents/Git_Local_Repos/mhl-suite/src/mhl_suite/xsd/MediaHashList_v1_1.xsd"
    ]
    for path in local_paths:
        if os.path.exists(path):
            return path
    sys.stderr.write(f"Debug: Looked for XSD at {local_paths}\n")
        
    return None

# Help menu
class MHLParser(argparse.ArgumentParser):
    def format_help(self):
        return (f"simple-mhl v{VERSION}. Modern verification and sealing tool for legacy MHL files\n"
                "\nUsage: simple-mhl <command> [options] <path>\n"
                ""
                "\nCommands:\n"
                "  seal              : Seal directory (MHL file generated at the root)\n"
                "    -a, --algorithm : Hash algorithm: xxhash64 (default), md5, sha1\n"
                "    --dont-reseal   : Abort operation if an MHL file already exists at root\n"
                "  verify            : Verify an MHL file\n"
                "  xsd-schema-check  : Validation of XML Schema Definition (XSD)\n"
                ""
                "\nGlobal options:\n"
                "  -h, --help        : Show this help message\n"
                "  --version         : Print version\n")

def main():
    # Use a single parser for all options
    parser = MHLParser(add_help=False)
    parser.add_argument("command", choices=["seal", "verify", "xsd-schema-check"], nargs="?", help="Command to run")
    parser.add_argument("path", nargs="?", help="Path to directory or MHL file")
    parser.add_argument("-a", "--algorithm", default="xxhash")
    parser.add_argument("--dont-reseal", action="store_true")
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("-h", "--help", action="store_true")

    args = parser.parse_args()

    # Handle help routing
    if args.help:
        print(parser.format_help())
        sys.exit(0)
    if not args.command or not args.path:
        sys.stderr.write("Error: Missing required arguments.\n\n")
        print(parser.format_help())
        sys.exit(1)

    match args.command:
        case "seal":
            seal(args.path, args.algorithm, args.dont_reseal)
        case "verify":
            verify(args.path)
        case "xsd-schema-check":
            validate_schema(args.path)
        case _:
            sys.exit(1)

# Define hash algorithms
ALGO_MAP = {
    "xxhash": (xxhash.xxh64, "xxhash64be"), "xxh64": (xxhash.xxh64, "xxhash64be"), "xxhash64": (xxhash.xxh64, "xxhash64be"), "xxhash64be": (xxhash.xxh64, "xxhash64be"),
#    "xxh128": (xxhash.xxh3_128, "xxhash128"), "xxhash128": (xxhash.xxh3_128, "xxhash128"),
#    "xxh3_64": (xxhash.xxh3_64, "xxhash3_64"), "xxhash3_64": (xxhash.xxh3_64, "xxhash3_64"),
    "md5": (hashlib.md5, "md5"),
    "sha1": (hashlib.sha1, "sha1"),
}

def get_hash(filepath, algo_key):
    if algo_key not in ALGO_MAP:
        raise ValueError(f"Unsupported hash algorithm: {algo_key}")

    # Instantiate the hasher and read the file in 64KB chunks (to maintain a low memory footprint)
    hasher_func = ALGO_MAP[algo_key][0]
    hasher = hasher_func()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

# ------------ Seal command ------------
def seal(root, algorithm, dont_reseal):
    # Resolve absolute path
    root = os.path.abspath(root)
    base_name = os.path.basename(root)

    # Generate timestamp
    now_dt = datetime.now(timezone.utc)
    timestamp = now_dt.strftime("%Y-%m-%d_%H%M%S")
    mhl_name = f"{base_name}_{timestamp}.mhl"
    mhl_path = os.path.join(root, mhl_name)
    
    # Handle filename collisions
    if os.path.exists(mhl_path):
        if dont_reseal:
            sys.exit(0)
        counter = 1
        while os.path.exists(os.path.join(root, f"{base_name}_{timestamp}_{counter}.mhl")):
            counter += 1
        mhl_path = os.path.join(root, f"{base_name}_{timestamp}_{counter}.mhl")

    # Initialise XML root element and populate the creatorinfo block
    now_iso = now_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    doc = etree.Element("hashlist", version="1.1") 
    etree.SubElement(doc, "creationdate").text = now_iso
    info = etree.SubElement(doc, "creatorinfo")
    for k, v in [
        ("username", getpass.getuser()), 
        ("hostname", platform.node()), 
        ("tool", f"simple-mhl v{VERSION}"), 
        ("startdate", now_iso), 
        ("finishdate", now_iso)
    ]:
        etree.SubElement(info, k).text = v
    xml_tag = ALGO_MAP.get(algorithm, (None, "xxhash64be"))[1]

    # Construct hash entries using os.walk efficiently
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        # Apply the original filtering logic to dirnames to keep os.walk in sync
        dirnames[:] = sorted([d for d in dirnames if not d.startswith('.')])
        
        for filename in sorted(filenames):
            # Apply original filtering logic to filenames
            if filename.startswith('.'):
                continue
                
            filepath = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(filepath, root)
            
            try:
                stat_result = os.stat(filepath)
            except OSError:
                continue
            
            # Create hash entry
            h_el = etree.SubElement(doc, "hash")
            etree.SubElement(h_el, "file").text = rel_path.replace('\\', '/')
            etree.SubElement(h_el, "size").text = str(stat_result.st_size)
            mtime_utc = datetime.fromtimestamp(stat_result.st_mtime, timezone.utc)
            etree.SubElement(h_el, "lastmodificationdate").text = mtime_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
            etree.SubElement(h_el, xml_tag).text = get_hash(filepath, algorithm)
            etree.SubElement(h_el, "hashdate").text = now_iso

    # Capture and update the finishdate after the os.walk loop completes
    finish_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    finish_el = info.find("finishdate")
    if finish_el is not None:
        finish_el.text = finish_iso
            
    # Serialise the constructed XML tree to disk with formatting
    etree.ElementTree(doc).write(mhl_path, xml_declaration=True, encoding='UTF-8', pretty_print=True)

# ------------ Verify command ------------
def verify(mhl_file):
    if not os.path.exists(mhl_file):
        sys.stderr.write(f"Verification Error: {mhl_file} not found\n")
        sys.exit(1)

    errors = []
    mhl_dir = os.path.abspath(os.path.dirname(mhl_file))
    try:
        # Parse the MHL file into a tree and conditionally evaluates it against the XSD
        try:
            tree = etree.parse(mhl_file)
        except etree.XMLSyntaxError:
            sys.exit(2)

        # Compare the declared payloads with the actual files
        hashes = tree.xpath("//*[local-name()='hash']")
        for h in hashes:
            # Extract the filename and skip the block if the file definition is missing
            fname_list = h.xpath(".//*[local-name()='file']/text()")
            if not fname_list:
                continue

            # Normalise path separators before executing joins (for Windows)
            fname = fname_list[0].replace('/', os.sep)
            
            # Use absolute path resolution and block directory traversal
            fpath = os.path.abspath(os.path.join(mhl_dir, fname))
            if os.path.commonpath([mhl_dir, fpath]) != mhl_dir:
                errors.append(f"Security: Blocked traversal attempt for {fname}")
                continue

            # Scan for supported hash algorithm tags
            h_nodes = h.xpath(".//*[local-name()='md5' or local-name()='sha1' or local-name()='xxhash' or local-name()='xxhash64' or local-name()='xxhash64be' or local-name()='xxhash128' or local-name()='xxhash3_64' or local-name()='null']")
            if not h_nodes:
                errors.append(f"No supported hash found for: {fname}")
                continue

            # Extract the specific tag string and its hex value
            h_node = h_nodes[0]
            tag = h_node.tag.split('}')[-1] if '}' in h_node.tag else h_node.tag
            expected = h_node.text
            
            # Compare hashes (verify physical existence on disk first)
            if not os.path.exists(fpath):
                errors.append(f"Missing file: {fname} cannot be found")
                continue
            calculated_hex = get_hash(fpath, tag)
            # Legacy check: <xxhash> was integer in some legacy MHL
            if tag == "xxhash" and expected.isdigit():
                if str(int(calculated_hex, 16)) != expected:
                    errors.append(fname)
            else:
                # Standard hex-to-hex comparison for all other tags
                if calculated_hex != expected:
                    errors.append(fname)

        # Exit with specific error codes
        if errors:
            print("\n".join(errors))
            sys.exit(40 if not [e for e in errors if "Missing" not in e] else 30)

        return
    except Exception as e:
        # Trap fatal execution errors for debugging
        sys.stderr.write(f"Verification Error: '{str(e)}'\n")
        raise

# ------------ Schema Validation ------------
def validate_schema(mhl_file):
    xsd_path = get_xsd_path()
    if not xsd_path:
        sys.stderr.write("Verification Error: Could not locate MediaHashList_v1_1.xsd\n")
        sys.exit(1)
    
    try:
        tree = etree.parse(mhl_file)
        xsd = etree.XMLSchema(etree.parse(xsd_path))
        if not xsd.validate(tree):
            for err in xsd.error_log:
                sys.stderr.write(f"Schema Error: {err.message} (line {err.line})\n")
            sys.exit(10)
    except (etree.XMLSyntaxError, OSError) as e:
        sys.stderr.write(f"XML Parsing Error: {e}\n")
        sys.exit(20)


# Boilerplate: direct execution only
if __name__ == "__main__":
    main()