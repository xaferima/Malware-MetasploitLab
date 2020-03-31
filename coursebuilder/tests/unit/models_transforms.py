# Copyright 2013 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Unit tests for the transforms functions."""

__author__ = 'John Orr (jorr@google.com)'

import datetime
import unittest
from models import transforms


def wrap_properties(properties):
    return {'properties': properties}


class JsonToDictTests(unittest.TestCase):

    def test_missing_optional_fields_are_allowed(self):
        schema = wrap_properties(
            {'opt_field': {'type': 'boolean', 'optional': 'true'}})
        result = transforms.json_to_dict({}, schema)
        self.assertEqual(len(result), 0)

    def test_missing_required_fields_are_rejected(self):
        schema = wrap_properties(
            {'req_field': {'type': 'boolean', 'optional': 'false'}})
        try:
            transforms.json_to_dict({}, schema)
            self.fail('Expected ValueError')
        except ValueError as e:
            self.assertEqual(str(e), 'Missing required attribute: req_field')

        schema = wrap_properties(
            {'req_field': {'type': 'boolean'}})
        try:
            transforms.json_to_dict({}, schema)
            self.fail('Expected ValueError')
        except ValueError as e:
            self.assertEqual(str(e), 'Missing required attribute: req_field')

    def test_convert_boolean(self):
        schema = wrap_properties({'field': {'type': 'boolean'}})
        source = {'field': True}
        result = transforms.json_to_dict(source, schema)
        self.assertEqual(len(result), 1)
        self.assertEqual(result['field'], True)

    def test_convert_string_to_boolean(self):
        schema = wrap_properties({'field': {'type': 'boolean'}})
        source = {'field': 'true'}
        result = transforms.json_to_dict(source, schema)
        self.assertEqual(len(result), 1)
        self.assertEqual(result['field'], True)

    def test_reject_bad_boolean(self):
        schema = wrap_properties({'field': {'type': 'boolean'}})
        source = {'field': 'cat'}
        try:
            transforms.json_to_dict(source, schema)
            self.fail('Expected ValueException')
        except ValueError as e:
            self.assertEqual(str(e), 'Bad boolean value for field: cat')

    def test_convert_number(self):
        schema = wrap_properties({'field': {'type': 'number'}})
        source = {'field': 3.14}
        result = transforms.json_to_dict(source, schema)
        self.assertEqual(len(result), 1)
        self.assertEqual(result['field'], 3.14)

    def test_convert_string_to_number(self):
        schema = wrap_properties({'field': {'type': 'number'}})
        source = {'field': '3.14'}
        result = transforms.json_to_dict(source, schema)
        self.assertEqual(len(result), 1)
        self.assertEqual(result['field'], 3.14)

    def test_reject_bad_number(self):
        schema = wrap_properties({'field': {'type': 'number'}})
        source = {'field': 'cat'}
        try:
            transforms.json_to_dict(source, schema)
            self.fail('Expected ValueException')
        except ValueError as e:
            self.assertEqual(str(e), 'could not convert string to float: cat')

    def test_convert_date(self):
        schema = wrap_properties({'field': {'type': 'date'}})
        source = {'field': '2005/03/01'}
        result = transforms.json_to_dict(source, schema)
        self.assertEqual(len(result), 1)
        self.assertEqual(result['field'], datetime.date(2005, 3, 1))

    def test_reject_bad_dates(self):
        schema = wrap_properties({'field': {'type': 'date'}})
        source = {'field': '2005/02/31'}
        try:
            transforms.json_to_dict(source, schema)
            self.fail('Expected ValueException')
        except ValueError as e:
            self.assertEqual(str(e), 'day is out of range for month')

        schema = wrap_properties({'field': {'type': 'date'}})
        source = {'field': 'cat'}
        try:
            transforms.json_to_dict(source, schema)
            self.fail('Expected ValueException')
        except ValueError as e:
            self.assertEqual(
                str(e), 'time data \'cat\' does not match format \'%Y/%m/%d\'')

    def test_convert_datetime(self):
        schema = wrap_properties({'field': {'type': 'datetime'}})
        source = {'field': '2005/03/01 20:30'}
        result = transforms.json_to_dict(source, schema)
        self.assertEqual(len(result), 1)
        self.assertEqual(
            result['field'], datetime.datetime(2005, 3, 1, 20, 30, 0))

    def test_reject_bad_datetimes(self):
        schema = wrap_properties({'field': {'type': 'datetime'}})
        source = {'field': '2005/02/31 20:30'}
        try:
            transforms.json_to_dict(source, schema)
            self.fail('Expected ValueException')
        except ValueError as e:
            self.assertEqual(str(e), 'day is out of range for month')

        schema = wrap_properties({'field': {'type': 'datetime'}})
        source = {'field': 'cat'}
        try:
            transforms.json_to_dict(source, schema)
            self.fail('Expected ValueException')
        except ValueError as e:
            self.assertEqual(
                str(e),
                'time data \'cat\' does not match format \'%Y/%m/%d %H:%M\'')


class StringValueConversionTests(unittest.TestCase):

    def test_value_to_string(self):
        assert transforms.value_to_string(True, bool) == 'True'
        assert transforms.value_to_string(False, bool) == 'False'
        assert transforms.value_to_string(None, bool) == 'False'

    def test_string_to_value(self):
        assert transforms.string_to_value('True', bool)
        assert transforms.string_to_value('1', bool)
        assert transforms.string_to_value(1, bool)

        assert not transforms.string_to_value('False', bool)
        assert not transforms.string_to_value('0', bool)
        assert not transforms.string_to_value('5', bool)
        assert not transforms.string_to_value(0, bool)
        assert not transforms.string_to_value(5, bool)
        assert not transforms.string_to_value(None, bool)

        assert transforms.string_to_value('15', int) == 15
        assert transforms.string_to_value(15, int) == 15
        assert transforms.string_to_value(None, int) == 0

        assert transforms.string_to_value('foo', str) == 'foo'
        assert transforms.string_to_value(None, str) == str('')


class JsonParsingTests(unittest.TestCase):

    def test_json_trailing_comma_in_dict_fails(self):
        json_text = '{"foo": "bar",}'
        try:
            transforms.loads(json_text)
            raise Exception('Expected to fail')
        except ValueError:
            pass

    def test_json_trailing_comma_in_array_fails(self):
        json_text = '{"foo": ["bar",]}'
        try:
            transforms.loads(json_text)
            raise Exception('Expected to fail')
        except ValueError:
            pass

    def test_non_strict_mode_parses_json(self):
        json_text = '{"foo": "bar", "baz": ["bum",],}'
        _json = transforms.loads(json_text, strict=False)
        assert _json.get('foo') == 'bar'
