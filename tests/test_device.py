"""Sidecar builders, listing parser, folder lookup and the retention guard (stdlib only)."""
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rmsend_lib import config, device  # noqa: E402


def doc(doc_id, name, parent="", kind="DocumentType", modified=0, deleted=False):
    return device.RemoteDoc(doc_id, name, parent, kind, modified, deleted)


class SidecarTests(unittest.TestCase):
    def test_metadata_carries_parent_and_type(self):
        meta = json.loads(device.build_metadata("Paper — 18 Sep", parent="abc"))
        self.assertEqual(meta["parent"], "abc")
        self.assertEqual(meta["type"], "DocumentType")
        self.assertEqual(meta["visibleName"], "Paper — 18 Sep")
        self.assertFalse(meta["deleted"])
        self.assertEqual(meta["createdTime"], meta["lastModified"])

    def test_content_epub_cover_and_size(self):
        content = json.loads(device.build_content("t", "epub", 1234))
        self.assertEqual(content["coverPageNumber"], -1)
        self.assertEqual(content["sizeInBytes"], "1234")
        self.assertEqual(content["fileType"], "epub")

    def test_bundle_can_mint_the_folder_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            a = work / "a.pdf"
            a.write_bytes(b"%PDF-1.4 a")
            bundle = device.build_bundle((device.Outgoing(a, "A"),), "fid", work, new_folder=("Daily Paper", "fid"))
            with tarfile.open(bundle) as archive:
                names = archive.getnames()
                meta = json.loads(archive.extractfile("fid.metadata").read())
        self.assertEqual(len(names), 5)
        self.assertEqual(meta["type"], "CollectionType")
        self.assertEqual(meta["visibleName"], "Daily Paper")
        self.assertEqual(meta["parent"], "")

    def test_bundle_holds_three_files_per_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            a, b = work / "a.pdf", work / "b.pdf"
            a.write_bytes(b"%PDF-1.4 a")
            b.write_bytes(b"%PDF-1.4 b")
            bundle = device.build_bundle((device.Outgoing(a, "A"), device.Outgoing(b, "B")), "folder", work)
            with tarfile.open(bundle) as archive:
                names = archive.getnames()
        self.assertEqual(len(names), 6)
        self.assertEqual(sum(n.endswith(".pdf") for n in names), 2)
        self.assertEqual(sum(n.endswith(".metadata") for n in names), 2)
        self.assertEqual(sum(n.endswith(".content") for n in names), 2)


class ListingTests(unittest.TestCase):
    def test_parse_listing_skips_torn_lines(self):
        text = ("id1\t" + json.dumps({"visibleName": "Daily Paper", "type": "CollectionType",
                                        "parent": "", "lastModified": "5"}) + "\n"
                "id2\t{not json\n"
                "id3\t" + json.dumps({"visibleName": "X", "type": "DocumentType", "parent": "id1",
                                        "lastModified": "7", "deleted": True}) + "\n")
        docs = device.parse_listing(text)
        self.assertEqual([d.id for d in docs], ["id1", "id3"])
        self.assertTrue(docs[1].deleted)
        self.assertEqual(docs[0].last_modified, 5)

    def test_find_folder_ignores_documents_and_deleted_folders(self):
        docs = (doc("f-old", "Daily Paper", kind="CollectionType", deleted=True),
                doc("d1", "Daily Paper"),
                doc("f", "Daily Paper", kind="CollectionType"))
        self.assertEqual(device.find_folder(docs, "Daily Paper"), "f")
        self.assertIsNone(device.find_folder(docs, "Other"))


class RetentionTests(unittest.TestCase):
    docs = (
        doc("p1", "Belisario Daily — Mon", parent="f", modified=1),
        doc("p2", "Belisario Daily — Tue", parent="f", modified=2),
        doc("p3", "Belisario Daily — Wed", parent="f", modified=3),
        doc("p4", "Belisario Daily — Thu", parent="f", modified=4),
        doc("other", "Belisario Daily — stray", parent="elsewhere", modified=9),
        doc("note", "My notes", parent="f", modified=9),
        doc("gone", "Belisario Daily — old", parent="f", modified=0, deleted=True),
    )

    def test_keeps_newest_n_only_within_folder_and_prefix(self):
        self.assertEqual(device.select_prunable(self.docs, "f", 2, "Belisario Daily"), ("p2", "p1"))

    def test_nothing_to_prune_is_idempotent(self):
        self.assertEqual(device.select_prunable(self.docs, "f", 4, "Belisario Daily"), ())
        self.assertEqual(device.select_prunable((), "f", 1, "Belisario Daily"), ())

    def test_keep_zero_or_negative_prunes_everything_matching(self):
        self.assertEqual(len(device.select_prunable(self.docs, "f", 0, "Belisario Daily")), 4)
        self.assertEqual(len(device.select_prunable(self.docs, "f", -1, "Belisario Daily")), 4)

    def test_prune_commands(self):
        self.assertEqual(device._prune_command((), "rm"), "")
        rm = device._prune_command(("a b", "c"), "rm")
        self.assertIn("rm -rf \"$i\" \"$i\".*", rm)
        self.assertIn("'a b' c", rm)
        trash = device._prune_command(("a",), "trash")
        self.assertIn(config.TRASH_PARENT, trash)
        self.assertIn("sed -i", trash)


if __name__ == "__main__":
    unittest.main()
