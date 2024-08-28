import json

from sqlalchemy.types import TypeDecorator
from sqlalchemy import UnicodeText


class JSONType(TypeDecorator):
    # pylint: disable=abstract-method

    impl = UnicodeText

    def process_bind_param(self, value, dialect):
        # it may seem natural to use ensure_ascii=False here given UnicodeText
        # above, but  it's actually slower than ensure_ascii=True in
        # python 2 (!)
        return json.dumps(
            value, skipkeys=True, sort_keys=True)

    def process_result_value(self, value, dialect):
        return json.loads(value)
