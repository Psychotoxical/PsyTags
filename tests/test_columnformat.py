import unittest
from types import SimpleNamespace as NS

from psytags.columnformat import format as fmt


def track(**fields):
    return NS(field=lambda name: fields.get(name.upper(), []))


class ColumnFormatTests(unittest.TestCase):
    def test_a_field_shows_its_first_value(self):
        self.assertEqual(fmt("%title%", track(TITLE=["One", "Two"])), "One")

    def test_a_missing_field_is_empty(self):
        self.assertEqual(fmt("%title%", track()), "")

    def test_text_around_a_field_stays(self):
        self.assertEqual(fmt("%_bitrate% kbit/s", track(_BITRATE=["320"])), "320 kbit/s")

    def test_an_optional_part_shows_when_its_field_has_a_value(self):
        self.assertEqual(fmt("%_tag_read%[ (%_tag%)]", track(_TAG_READ=["ID3v2"], _TAG=["ID3v1"])), "ID3v2 (ID3v1)")

    def test_an_optional_part_vanishes_when_its_field_is_empty(self):
        self.assertEqual(fmt("%_tag_read%[ (%_tag%)]", track(_TAG_READ=["ID3v2"])), "ID3v2")

    def test_meta_sep_joins_all_values(self):
        self.assertEqual(fmt("$meta_sep(artist,\\\\)", track(ARTIST=["Ann", "Bob"])), "Ann\\\\Bob")

    def test_meta_sep_counts_inside_an_optional_part(self):
        self.assertEqual(fmt("[x$meta_sep(artist,-)]", track()), "")
        self.assertEqual(fmt("[x$meta_sep(artist,-)]", track(ARTIST=["A"])), "xA")

    def test_num_pads_the_leading_number(self):
        self.assertEqual(fmt("$num(%track%,3)", track(TRACK=["7/12"])), "007")

    def test_num_of_nothing_is_zero(self):
        self.assertEqual(fmt("$num(%track%,3)", track()), "000")

    def test_a_stray_percent_sign_is_text(self):
        self.assertEqual(fmt("100%", track()), "100%")

    def test_other_dollar_text_stays_as_it_is(self):
        self.assertEqual(fmt("$upper(x)", track()), "$upper(x)")


if __name__ == "__main__":
    unittest.main()
