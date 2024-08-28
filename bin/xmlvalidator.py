#!/usr/bin/python

import argparse
from lxml.etree import parse, XMLSchema, DocumentInvalid


class XMLValidator(object):

    def __init__(self, xml_path, schema_path):
        self._xml_path = xml_path
        self._schema_path = schema_path

    def _log(self, *args):
        l = [str(arg) for arg in args]
        print " ".join(l)

    def validate(self):
        try:
            schema_doc = parse(open(self._schema_path, "r"))
        except Exception, e:
            self._log("can't parse schema:", e)
            return

        schema = XMLSchema(schema_doc)

        try:
            doc = parse(open(self._xml_path, "r"))
        except Exception, e:
            self._log("can't parse XML document:", e)
            return

        try:
            schema.assertValid(doc)
        except DocumentInvalid, e:
            self._log("can't validate XML document:", e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("xml_path", help="path of XML document")
    parser.add_argument("schema_path", help="path of XML schema")
    ns = parser.parse_args()
    XMLValidator(ns.xml_path, ns.schema_path).validate()
