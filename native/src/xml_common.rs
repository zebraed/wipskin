//! Shared helpers for the XML writers in skin_xml.rs and deformer_xml.rs.

use pyo3::exceptions::PyIOError;
use pyo3::PyErr;
use std::borrow::Cow;
use std::fmt::Display;

/// Map any Display-able error (std::io::Error from the streaming XML
/// writers' writeln! calls, quick_xml::Error from Reader::from_file, etc.)
/// to a Python IOError.
pub fn io_err<E: Display>(e: E) -> PyErr {
    PyIOError::new_err(e.to_string())
}

/// Escape XML attribute-value special characters. Node/attribute names in
/// these files (joint names, deformer names, file paths) are not expected to
/// contain them, but escaping is cheap correctness insurance for values that
/// theoretically could (e.g. long DAG paths).
pub fn escape_attr(value: &str) -> Cow<'_, str> {
    if value.bytes().any(|b| matches!(b, b'&' | b'<' | b'>' | b'"')) {
        Cow::Owned(
            value
                .replace('&', "&amp;")
                .replace('<', "&lt;")
                .replace('>', "&gt;")
                .replace('"', "&quot;"),
        )
    } else {
        Cow::Borrowed(value)
    }
}

#[cfg(test)]
#[path = "xml_common_tests.rs"]
mod tests;
