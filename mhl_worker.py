#!/usr/bin/env python3
# MHL worker. This script is called automatically by mhlver to verify traditional MHL files.
import os, struct, sys, xxhash, hashlib
try:
    from lxml import etree
except ImportError:
    # Exit 1 signals a missing dependency to Bash
    sys.exit(1)

# CUSTOMISATION of Media Hash List v1.1 XML Schema Definition (XSD) to prevent failures with optional elements
MHL_XSD = """
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="md5Type"><xs:restriction base="xs:hexBinary"><xs:length value="16"/></xs:restriction></xs:simpleType>
  <xs:simpleType name="sha1Type"><xs:restriction base="xs:hexBinary"><xs:length value="20"/></xs:restriction></xs:simpleType>
  <xs:simpleType name="xxhashType"><xs:restriction base="xs:integer"><xs:totalDigits value="10"/></xs:restriction></xs:simpleType>
  <xs:simpleType name="xxhash64Type"><xs:restriction base="xs:hexBinary"><xs:length value="8"/></xs:restriction></xs:simpleType>
  <xs:simpleType name="versionType"><xs:restriction base="xs:decimal"><xs:fractionDigits value="1"/><xs:minInclusive value="0"/></xs:restriction></xs:simpleType>

  <xs:element name="hashlist">
    <xs:complexType>
      <xs:choice maxOccurs="unbounded">
        <xs:element name="creationdate" type="xs:dateTime" minOccurs="0"/>
        <xs:element name="creatorinfo" minOccurs="0">
          <xs:complexType>
            <xs:choice maxOccurs="unbounded">
              <xs:element name="name" type="xs:string" minOccurs="0"/>
              <xs:element name="username" type="xs:string"/>
              <xs:element name="hostname" type="xs:string"/>
              <xs:element name="tool" type="xs:string"/>
              <xs:element name="source" type="xs:string" minOccurs="0"/>
              <xs:element name="startdate" type="xs:dateTime"/>
              <xs:element name="finishdate" type="xs:dateTime"/>
              <xs:element name="log" type="xs:string" minOccurs="0"/>
            </xs:choice>
          </xs:complexType>
        </xs:element>
        <xs:element name="hash" maxOccurs="unbounded">
          <xs:complexType>
            <xs:choice maxOccurs="unbounded">
              <xs:element name="file" type="xs:string"/>
              <xs:element name="size" type="xs:positiveInteger"/>
              <xs:element name="creationdate" type="xs:dateTime" minOccurs="0"/>
              <xs:element name="lastmodificationdate" type="xs:dateTime" minOccurs="0"/>
              <xs:element name="md5" type="md5Type" minOccurs="0"/>
              <xs:element name="sha1" type="sha1Type" minOccurs="0"/>
              <xs:element name="xxhash" type="xxhashType" minOccurs="0"/>
              <xs:element name="xxhash64" type="xxhash64Type" minOccurs="0"/>
              <xs:element name="xxhash64be" type="xxhash64Type" minOccurs="0"/>
              <xs:element name="hashdate" type="xs:dateTime" minOccurs="0"/>
            </xs:choice>
            <xs:attribute name="referencehhashlist" type="xs:boolean"/>
          </xs:complexType>
        </xs:element>
      </xs:choice>
      <xs:attribute name="version" type="versionType" use="required"/>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""

def verify_hashes(doc, mhl_path):
    base_dir = os.path.dirname(os.path.abspath(mhl_path))
    success = True
    supported_tags = ['xxhash64be', 'xxhash64', 'md5', 'sha1', 'xxhash']

    for hash_entry in doc.findall('hash'):
        file_el = hash_entry.find('file')
        if file_el is None: continue
        filename = file_el.text
        file_path = os.path.join(base_dir, filename)
        
        hash_el = None
        algo = None
        for tag in supported_tags:
            hash_el = hash_entry.find(tag)
            if hash_el is not None:
                algo = tag
                break
        
        if hash_el is None or not os.path.exists(file_path):
            if hash_el is not None: print(f"MISSING: {filename}")
            success = False
            continue

        expected = hash_el.text.strip().lower()

        if algo in ['xxhash64be', 'xxhash64']: hasher = xxhash.xxh64()
        elif algo == 'xxhash': hasher = xxhash.xxh32()
        elif algo == 'md5': hasher = hashlib.md5()
        elif algo == 'sha1': hasher = hashlib.sha1()
        else: continue

        try:
            with open(file_path, 'rb') as f:
                while chunk := f.read(1024 * 1024):
                    hasher.update(chunk)
        except Exception:
            success = False
            continue

        if algo == 'xxhash64be': actual = struct.pack('>Q', hasher.intdigest()).hex()
        elif algo == 'xxhash64': actual = struct.pack('<Q', hasher.intdigest()).hex()
        elif algo == 'xxhash': actual = struct.pack('>I', hasher.intdigest()).hex()
        else: actual = hasher.hexdigest()

        if actual != expected:
            print(f"MISMATCH: {filename} ({algo.upper()} Exp: {expected}, Got: {actual})")
            success = False
    return success

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    mhl_file = sys.argv[-1]
    
    schema_ok = True
    doc = None

    # 1. Parsing Phase
    try:
        parser = etree.XMLParser(recover=True, remove_blank_text=True, resolve_entities=False)
        with open(mhl_file, 'rb') as f:
            xml_data = f.read()
        doc = etree.fromstring(xml_data, parser=parser)
    except Exception:
        sys.exit(20) # Actual unparseable XML

    if doc is None:
        sys.exit(20)

    # 2. Validation Phase
    try:
        schema_root = etree.XML(MHL_XSD.encode('utf-8'))
        schema = etree.XMLSchema(schema_root)
        if not schema.validate(doc):
            schema_ok = False
    except Exception:
        # Schema definition failure (Signature or double-h typo)
        schema_ok = False

    # 3. Hash Phase
    hashes_ok = verify_hashes(doc, mhl_file)

    # 4. Bitwise Return Codes
    if hashes_ok and schema_ok:
        sys.exit(0)
    elif hashes_ok and not schema_ok:
        sys.exit(10) # Verified but non-compliant
    elif not hashes_ok and schema_ok:
        sys.exit(30) # Corrupt data
    else:
        sys.exit(40) # Both fail