#!/usr/bin/env python

import argparse
import logging

from litp.core.schemawriter import SchemaWriter


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("schema_path",
                        help="path of generated XML schema files")
    parser.add_argument("litp_path",
                        nargs="+",
                        help="path of litp")
    parser.add_argument("-d", "--debug", action="store_true",
                        help="debug mode")
    ns = parser.parse_args()

    if ns.debug:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.INFO
    logging.basicConfig(level=loglevel)

    writer = SchemaWriter(ns.schema_path, ns.litp_path)
    writer.write()
