"""
Benchmark the weight-file list scan+classify path (Maya-free).

Compares the old predicate (a full xml.etree parse of every file) against the
new xml_sniff path (first-tag sniff + (mtime, size) cache) that backs
is_skin_weight_file / is_deformer_weight_file after the Phase 1 changes.

Run:
    python wipskin/scripts/bench_listing.py [file_count] [points_per_file]
"""

import os
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from wipskin.formats import xml_sniff
from wipskin.models import weight_files


def _write_synthetic_skin_xml(path, points):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write('<?xml version="1.0" encoding="utf-8"?>\n<deformerWeight>\n')
        handle.write('  <deformer name="body_skinCluster">\n')
        handle.write('    <attribute name="maxInfluences" value="4"/>\n')
        handle.write('  </deformer>\n')
        handle.write('  <shape name="body_geoShape" size="%d"/>\n' % points)
        for source in ("joint_1", "joint_2", "joint_3"):
            handle.write('  <weights source="%s" shape="body_geoShape">\n' % source)
            for index in range(points):
                handle.write('    <point index="%d" value="0.333"/>\n' % index)
            handle.write('  </weights>\n')
        handle.write('</deformerWeight>\n')


def _old_predicate(path):
    """The pre-Phase-1 predicate: full DOM parse to read the root tag."""
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError):
        return False
    return tree.getroot().tag == "deformerWeight"


def _new_predicate(path):
    return xml_sniff.has_root_tag(path, "deformerWeight")


def _time_scan(directory, predicate):
    start = time.perf_counter()
    names = weight_files.scan_weight_files(directory, ["xml"], predicate=predicate)
    elapsed = time.perf_counter() - start
    return elapsed, len(names)


def main():
    file_count = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    points = int(sys.argv[2]) if len(sys.argv) > 2 else 500

    with tempfile.TemporaryDirectory() as directory:
        print("Generating %d synthetic skin XML files (%d points each)..."
              % (file_count, points))
        for i in range(file_count):
            _write_synthetic_skin_xml(
                os.path.join(directory, "mesh_%05d.xml" % i), points
            )

        old_elapsed, old_n = _time_scan(directory, _old_predicate)

        xml_sniff.clear_cache()
        cold_elapsed, cold_n = _time_scan(directory, _new_predicate)
        warm_elapsed, warm_n = _time_scan(directory, _new_predicate)

        assert old_n == cold_n == warm_n == file_count, (old_n, cold_n, warm_n)

        print()
        print("Files listed: %d" % file_count)
        print("  old (full ET.parse each)     : %8.1f ms" % (old_elapsed * 1000))
        print("  new cold (sniff, empty cache): %8.1f ms  (%.1fx faster)"
              % (cold_elapsed * 1000, old_elapsed / cold_elapsed))
        print("  new warm (cache hit)         : %8.1f ms  (%.1fx faster)"
              % (warm_elapsed * 1000, old_elapsed / max(warm_elapsed, 1e-9)))


if __name__ == "__main__":
    main()
