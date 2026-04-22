#!/usr/bin/env python3
# simple-mhl - Modern verification and sealing tool for legacy MHL files

import os, sys
import argparse, getpass, platform, hashlib, xxhash
from datetime import datetime, timezone

try:
    from lxml import etree
except ImportError:
    sys.exit(1)

VERSION = "1.0"
MHL_NS = "http://www.mediahashlist.org/v1.1"

# MHL v1.1 XSD (XMLDSig stripped so it works offline)
MHL_XSD = f"""
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" 
           targetNamespace="{MHL_NS}" 
           xmlns="{MHL_NS}" 
           elementFormDefault="qualified">
  <xs:simpleType name="md5Type"><xs:restriction base="xs:hexBinary"><xs:length value="16"/></xs:restriction></xs:simpleType>
  <xs:simpleType name="sha1Type"><xs:restriction base="xs:hexBinary"><xs:length value="20"/></xs:restriction></xs:simpleType>
  <xs:simpleType name="xxhashType"><xs:restriction base="xs:integer"><xs:totalDigits value="10"/></xs:restriction></xs:simpleType>
  <xs:simpleType name="xxhash64Type"><xs:restriction base="xs:hexBinary"><xs:length value="8"/></xs:restriction></xs:simpleType>
  <xs:simpleType name="versionType"><xs:restriction base="xs:decimal"><xs:fractionDigits value="1"/><xs:minInclusive value="0"/></xs:restriction></xs:simpleType>
  <xs:element name="creationdate" type="xs:dateTime"/>
  <xs:element name="file" type="xs:string"/>
  <xs:element name="size" type="xs:positiveInteger"/>
  <xs:element name="lastmodificationdate" type="xs:dateTime"/>
  <xs:element name="hashdate" type="xs:dateTime"/>
  <xs:element name="name" type="xs:string"/>
  <xs:element name="username" type="xs:string"/>
  <xs:element name="hostname" type="xs:string"/>
  <xs:element name="tool" type="xs:string"/>
  <xs:element name="source" type="xs:string"/>
  <xs:element name="startdate" type="xs:dateTime"/>
  <xs:element name="finishdate" type="xs:dateTime"/>
  <xs:element name="log" type="xs:string"/>
  <xs:attribute name="version" type="versionType"/>
  <xs:attribute name="referencehhashlist" type="xs:boolean"/>
  <xs:element name="md5"><xs:complexType><xs:simpleContent><xs:extension base="md5Type"/></xs:simpleContent></xs:complexType></xs:element>
  <xs:element name="sha1"><xs:complexType><xs:simpleContent><xs:extension base="sha1Type"/></xs:simpleContent></xs:complexType></xs:element>
  <xs:element name="xxhash"><xs:complexType><xs:simpleContent><xs:extension base="xxhashType"/></xs:simpleContent></xs:complexType></xs:element>
  <xs:element name="xxhash64"><xs:complexType><xs:simpleContent><xs:extension base="xxhash64Type"/></xs:simpleContent></xs:complexType></xs:element>
  <xs:element name="xxhash64be"><xs:complexType><xs:simpleContent><xs:extension base="xxhash64Type"/></xs:simpleContent></xs:complexType></xs:element>
  <xs:element name="null" type="xs:string" fixed=""/>
  <xs:element name="creatorinfo">
    <xs:complexType><xs:sequence>
      <xs:element ref="name" minOccurs="0" maxOccurs="1"/>
      <xs:element ref="username" minOccurs="1" maxOccurs="1"/>
      <xs:element ref="hostname" minOccurs="1" maxOccurs="1"/>
      <xs:element ref="tool" minOccurs="1" maxOccurs="1"/>
      <xs:element ref="source" minOccurs="0" maxOccurs="1"/>
      <xs:element ref="startdate" minOccurs="1" maxOccurs="1"/>
      <xs:element ref="finishdate" minOccurs="1" maxOccurs="1"/>
      <xs:element ref="log" minOccurs="0" maxOccurs="1"/>
    </xs:sequence></xs:complexType>
  </xs:element>
  <xs:element name="hash">
    <xs:complexType><xs:sequence>
      <xs:element ref="file" minOccurs="1" maxOccurs="1"/>
      <xs:element ref="size" minOccurs="1" maxOccurs="1"/>
      <xs:element ref="creationdate" minOccurs="0" maxOccurs="1"/>
      <xs:element ref="lastmodificationdate"/>
      <xs:choice minOccurs="1" maxOccurs="unbounded">
        <xs:element ref="md5"/><xs:element ref="sha1"/><xs:element ref="xxhash"/><xs:element ref="xxhash64"/><xs:element ref="xxhash64be"/><xs:element ref="null"/>
      </xs:choice>
      <xs:element ref="hashdate"/>
    </xs:sequence><xs:attribute ref="referencehhashlist"/></xs:complexType>
  </xs:element>
  <xs:element name="hashlist">
    <xs:complexType><xs:sequence>
      <xs:element ref="creationdate" minOccurs="0" maxOccurs="1"/>
      <xs:element ref="creatorinfo" minOccurs="1" maxOccurs="1"/>
      <xs:element ref="hash" minOccurs="1" maxOccurs="unbounded"/>
    </xs:sequence><xs:attribute name="version" type="versionType" use="required"/></xs:complexType>
  </xs:element>
</xs:schema>
"""

# Help menu
class MHLParser(argparse.ArgumentParser):
    def format_help(self):
        return (f"simple-mhl v{VERSION}. Modern verification and sealing tool for legacy MHL files\n"
                "\nUsage: simple-mhl <command> [options] <path>\n"
                "\nCommands & Options:\n"
                "  seal               : Seal directory (MHL file will be generated at the root)\n"
                "    -a, --algorithm  : Algorithm: xxhash (default), md5, sha1, xxh128, xxh3_64\n"
                "    --dont-reseal    : Abort operation if an MHL file already exists at root\n"
                "  verify             : Verify an MHL file and hash values\n"
                "    -s, --schema     : Validate XML against MHL v1.1 XSD\n"
                "  -h, --help         : Show this help message\n"
                "  --version          : Print version\n")

def main():
    parser = MHLParser(add_help=False)
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("-h", "--help", action="help")
    
    subparsers = parser.add_subparsers(dest="command")
    
    # Seal Command Parsing
    s_parser = subparsers.add_parser("seal", add_help=False)
    s_parser.add_argument("path")
    s_parser.add_argument("-a", "--algorithm", default="xxhash")
    s_parser.add_argument("--dont-reseal", action="store_true")
    s_parser.add_argument("-h", "--help", action="store_true")

    # Verify Command Parsing
    v_parser = subparsers.add_parser("verify", add_help=False)
    v_parser.add_argument("path")
    v_parser.add_argument("-s", "--schema", action="store_true")
    v_parser.add_argument("-h", "--help", action="store_true")

    args, unknown = parser.parse_known_args()

    # Handle help routing
    if not args.command or args.help:
        if args.command == "seal":
            print("Usage: simple-mhl seal [options] <directory>\n\nOptions:\n  -a, --algorithm   : Algorithm: xxhash (default), md5, sha1, xxh128, xxh3_64\n  --dont-reseal     : Abort operation if an MHL file already exists at root\n  -h, --help        : Show this message")
        elif args.command == "verify":
            print("Usage: simple-mhl verify [options] <file.mhl>\n\nOptions:\n  -s, --schema      : Validate XML against MHL v1.1 XSD\n  -h, --help        : Show this message")
        else:
            print(parser.format_help())
        return

    if args.command == "seal":
        seal(args.path, args.algorithm, args.dont_reseal)
    elif args.command == "verify":
        verify(args.path, args.schema)

# Define hash algorithms
def get_hash(filepath, algo_key):
    mapping = {
        "xxhash": xxhash.xxh64,
        "xxh64": xxhash.xxh64, "xxhash64": xxhash.xxh64, "xxhash64be": xxhash.xxh64,
        "xxh128": xxhash.xxh3_128, "xxhash128": xxhash.xxh3_128,
        "xxh3_64": xxhash.xxh3_64, "xxhash3_64": xxhash.xxh3_64,
        "md5": hashlib.md5,
        "sha1": hashlib.sha1,
    }
    if algo_key not in mapping:
        raise ValueError(f"Unsupported hash algorithm: {algo_key}")

    # Instantiate the hasher and read the file in 64KB chunks (to maintain a low memory footprint)
    hasher = mapping[algo_key]()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""): hasher.update(chunk)
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
        if dont_reseal: sys.exit(0)
        counter = 1
        while os.path.exists(os.path.join(root, f"{base_name}_{timestamp}_{counter}.mhl")):
            counter += 1
        mhl_path = os.path.join(root, f"{base_name}_{timestamp}_{counter}.mhl")

    # Initialise XML root element and populate the creatorinfo block
    now_iso = now_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    doc = etree.Element(f"{{{MHL_NS}}}hashlist", version="1.1", nsmap={None: MHL_NS})
    etree.SubElement(doc, f"{{{MHL_NS}}}creationdate").text = now_iso
    info = etree.SubElement(doc, f"{{{MHL_NS}}}creatorinfo")
    for k, v in [("username", getpass.getuser()), ("hostname", platform.node()), ("tool", f"simple-mhl v{VERSION}"), ("startdate", now_iso), ("finishdate", now_iso)]:
        etree.SubElement(info, f"{{{MHL_NS}}}{k}").text = v
    xml_tag = 'xxhash64be' if algorithm in ['xxhash', 'xxh64'] else algorithm.replace('xxh', 'xxhash')

    # Construct hash entries, ignoring hidden files
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = sorted([d for d in dirnames if not d.startswith('.')])
        
        with os.scandir(dirpath) as it:
            entries = {e.name: e for e in it if not e.name.startswith('.') and e.is_file()}
            
        for filename in sorted(entries.keys()):
            entry = entries[filename]
            filepath = entry.path
            
            # Calculate relative path for the XML manifest
            rel_path = os.path.relpath(filepath, root)
            
            stat_result = entry.stat()
            
            h_el = etree.SubElement(doc, f"{{{MHL_NS}}}hash")
            etree.SubElement(h_el, f"{{{MHL_NS}}}file").text = rel_path.replace('\\', '/')
            etree.SubElement(h_el, f"{{{MHL_NS}}}size").text = str(stat_result.st_size)
            mtime_utc = datetime.fromtimestamp(stat_result.st_mtime, timezone.utc)
            etree.SubElement(h_el, f"{{{MHL_NS}}}lastmodificationdate").text = mtime_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
            etree.SubElement(h_el, f"{{{MHL_NS}}}{xml_tag}").text = get_hash(filepath, algorithm)
            etree.SubElement(h_el, f"{{{MHL_NS}}}hashdate").text = now_iso
            
    # Capture and update the finishdate after the os.walk loop completes
    finish_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    info.find(f"{{{MHL_NS}}}finishdate").text = finish_iso
            
    # Serialise the constructed XML tree to disk with formatting
    etree.ElementTree(doc).write(mhl_path, xml_declaration=True, encoding='UTF-8', pretty_print=True)

# ------------ Verify command ------------
def verify(mhl_file, schema):
    errors, schema_ok = [], True
    mhl_dir = os.path.abspath(os.path.dirname(mhl_file))
    try:
        # Parse the MHL file into a tree and conditionally evaluates it against the  XSD
        tree = etree.parse(mhl_file)
        if schema:
            xsd_doc = etree.XML(MHL_XSD.encode('utf-8'))
            xsd = etree.XMLSchema(xsd_doc)
            if not xsd.validate(tree):
                schema_ok = False
                for err in xsd.error_log:
                    sys.stderr.write(f"Schema Error: {err.message.replace(f'{{{MHL_NS}}}', '')} (line {err.line})\n")

        # Compare the declared payloads with the actual files
        hashes = tree.xpath("//*[local-name()='hash']")
        for h in hashes:
            # Extract the filename and skip the block if the file definition is missing
            fname_list = h.xpath(".//*[local-name()='file']/text()")
            if not fname_list: continue
            fname = fname_list[0]
            
            # Use absolute path resolution and block directory traversal
            fpath = os.path.abspath(os.path.join(mhl_dir, fname))
            if not fpath.startswith(mhl_dir):
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
            sys.exit(40 if not schema_ok and not [e for e in errors if "Missing" not in e] else 30)
        
        sys.exit(10 if not schema_ok else 0)
    except Exception as e:
        # Trap fatal execution errors for debugging
        sys.stderr.write(f"Verification Error: '{str(e)}'\n")
        raise

# Boilerplate: direct execution only
if __name__ == "__main__":
    main()