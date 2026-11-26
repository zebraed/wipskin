//! Unit tests for xml_common.rs. Kept as a sibling file (declared via
//! `#[path = "xml_common_tests.rs"] mod tests;` in xml_common.rs) rather
//! than inline, so the source file stays focused on the implementation and
//! `use super::*` still gives these tests access to xml_common's private
//! items.

use super::*;

#[test]
fn escape_attr_passes_plain_text_through_unchanged() {
    assert_eq!(escape_attr("joint1"), "joint1");
}

#[test]
fn escape_attr_escapes_all_four_special_characters() {
    assert_eq!(escape_attr("a&b<c>d\"e"), "a&amp;b&lt;c&gt;d&quot;e");
}

#[test]
fn escape_attr_borrows_when_there_is_nothing_to_escape() {
    // No-op inputs should not allocate -- this is the common case (plain
    // joint/deformer names), so it matters for export throughput.
    assert!(matches!(escape_attr("plain"), Cow::Borrowed(_)));
}

#[test]
fn escape_attr_owns_when_escaping_happened() {
    assert!(matches!(escape_attr("a&b"), Cow::Owned(_)));
}

#[test]
fn io_err_can_be_constructed_without_a_python_interpreter() {
    // PyErr construction in PyO3 is lazy and must not need the GIL --
    // cargo test runs this crate's Rust logic standalone, with no
    // Python interpreter initialized at all. If that ever stopped being
    // true, every io_err() call in the writers would panic the moment
    // cargo test touched an error path. Deliberately not inspecting the
    // error's type or Display here -- either would need a real running
    // interpreter and could crash the test binary rather than fail it;
    // simply not panicking on construction is the whole point of this
    // test.
    let _err = io_err("disk full");
}
