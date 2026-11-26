//! wipskin_native: optional Rust accelerator for wipskin's XML weight IO.
//! Loaded from python/wipskin/_native/ (see xml_accel.py's dispatch layer,
//! at python/wipskin/formats/xml_accel.py); every entry point here has a
//! pure-Python fallback, so a missing/broken build of this module degrades
//! gracefully rather than breaking wipskin.
//!
//! Module layout (kept split so no single file grows unmanageably):
//!   - xml_common.rs   shared XML-writer helpers (attribute escaping, I/O
//!                     error mapping)
//!   - skin_xml.rs     skinCluster deformerWeights XML (Maya-native format,
//!                     <deformerWeight> root) -- read + write
//!   - deformer_xml.rs wipskin's own deformer-weight XML for
//!                     cluster/softMod/wrap/etc (<customDeformerWeight>
//!                     root, weightList-based) -- read + write


use pyo3::prelude::*;

mod deformer_xml;
mod skin_xml;
mod xml_common;

use pyo3::exceptions::{PyIOError, PyValueError};
use quick_xml::events::Event;
use quick_xml::reader::Reader;

/// Minimal PyO3 learning-step function; kept as a smoke test for the build.
#[pyfunction]
fn sum_as_string(a: usize, b: usize) -> PyResult<String> {
    Ok((a + b).to_string())
}

/// Count start tags (<tag ...> or <tag .../>) in an XML file. A learning
/// step before writing the real parsers: the minimal quick-xml usage
/// pattern (open a reader, loop over events, stop at Eof) they build on.
#[pyfunction]
fn count_elements(path: String) -> PyResult<usize> {
    let mut reader =
        Reader::from_file(&path).map_err(|e| PyIOError::new_err(e.to_string()))?;
    let mut buf = Vec::new();
    let mut count: usize = 0;
    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Eof) => break,
            Ok(Event::Start(_)) | Ok(Event::Empty(_)) => count += 1,
            Ok(_) => {}
            Err(e) => return Err(PyValueError::new_err(e.to_string())),
        }
        buf.clear();
    }
    Ok(count)
}

#[pymodule]
fn wipskin_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(sum_as_string, m)?)?;
    m.add_function(wrap_pyfunction!(count_elements, m)?)?;
    m.add_function(wrap_pyfunction!(skin_xml::build_weight_matrix, m)?)?;
    m.add_function(wrap_pyfunction!(skin_xml::write_skin_xml, m)?)?;
    m.add_function(wrap_pyfunction!(deformer_xml::read_deformer_weights, m)?)?;
    m.add_function(wrap_pyfunction!(deformer_xml::write_deformer_weight_xml, m)?)?;
    Ok(())
}
