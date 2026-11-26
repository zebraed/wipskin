//! wipskin's own deformer-weight XML (customDeformerWeight root), for
//! non-skinCluster deformers (cluster/softMod/wrap/etc, which expose a
//! single {node}.weightList[geoIndex].weights per shape -- NOT the
//! Maya-native <deformerWeight> format skin_xml.rs handles, and NOT
//! blendShape's inputTarget/targetWeights structure, which is out of scope
//! here and routed through cmds.deformerWeights instead; see
//! docs/OPTIMIZATION_TECHNIQUES.md).
//!
//! Format matches deformer.py's existing ElementTree-based writer
//! (_export_deformer_weight_xml): multi-shape safe, all <shape> blocks
//! written first, then all <weights> blocks. Unlike skin XML, weights are
//! dense (one <point> per vertex, no tolerance-based sparse omission) and
//! floats use a fixed 6-decimal format rather than deformer.py's original
//! variable-length str(float) (read-back is unaffected: values are always
//! float-parsed, only the on-disk digit count differs from files written by
//! the pure-Python path).

use crate::xml_common::{escape_attr, io_err};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use quick_xml::events::{BytesStart, Event};
use quick_xml::reader::Reader;
use std::io::Write as _;

/// Read a single shape's per-vertex weights from a wipskin deformer-weight
/// XML. Finds the <weights shape="shape_name"> block and reads its dense
/// <point index value> children into a flat Vec<f64> of length num_verts.
///
/// Unlike skin XML weights (sparse, tolerance-based), deformer.py's own
/// writer always emits one <point> per vertex, so a missing point is the
/// exception, not the rule; it defaults to 1.0 to match
/// deformer._read_deformer_weights' own default=1.0.
#[pyfunction]
pub fn read_deformer_weights(
    path: String,
    shape_name: String,
    num_verts: usize,
) -> PyResult<Vec<f64>> {
    let mut weights = vec![1.0f64; num_verts];

    let mut reader = Reader::from_file(&path).map_err(io_err)?;
    let mut buf = Vec::new();
    let mut in_target_block = false;

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Eof) => break,
            Ok(Event::Start(e)) if e.name().as_ref() == b"weights" => {
                in_target_block = weights_shape_matches(&e, &shape_name)?;
            }
            Ok(Event::End(e)) if e.name().as_ref() == b"weights" => {
                in_target_block = false;
            }
            Ok(Event::Empty(e)) if e.name().as_ref() == b"point" && in_target_block => {
                apply_deformer_point(&e, num_verts, &mut weights)?;
            }
            Ok(_) => {}
            Err(e) => return Err(PyValueError::new_err(e.to_string())),
        }
        buf.clear();
    }

    Ok(weights)
}

fn weights_shape_matches(e: &BytesStart, shape_name: &str) -> PyResult<bool> {
    for attr in e.attributes() {
        let attr = attr.map_err(|err| PyValueError::new_err(err.to_string()))?;
        if attr.key.as_ref() != b"shape" {
            continue;
        }
        let value = attr
            .unescape_value()
            .map_err(|err| PyValueError::new_err(err.to_string()))?;
        return Ok(value.as_ref() == shape_name);
    }
    Ok(false)
}

fn apply_deformer_point(e: &BytesStart, num_verts: usize, weights: &mut [f64]) -> PyResult<()> {
    let mut row: Option<usize> = None;
    let mut value: Option<f64> = None;
    for attr in e.attributes() {
        let attr = attr.map_err(|err| PyValueError::new_err(err.to_string()))?;
        let text = attr
            .unescape_value()
            .map_err(|err| PyValueError::new_err(err.to_string()))?;
        match attr.key.as_ref() {
            b"index" => row = text.trim().parse::<usize>().ok(),
            b"value" => value = text.trim().parse::<f64>().ok(),
            _ => {}
        }
    }
    if let (Some(row), Some(value)) = (row, value) {
        if row < num_verts {
            weights[row] = value;
        }
    }
    Ok(())
}

// deformer.py's own writer joins with " ".join(...) -- no trailing space,
// unlike write_skin_xml's Maya-matched trailing-space convention.
fn join_floats_no_trailing_space(values: &[f64]) -> String {
    values
        .iter()
        .map(|v| format!("{v:.6}"))
        .collect::<Vec<_>>()
        .join(" ")
}

fn join_usizes_no_trailing_space(values: &[usize]) -> String {
    values
        .iter()
        .map(|v| v.to_string())
        .collect::<Vec<_>>()
        .join(" ")
}

/// Write wipskin's own deformer-weight XML (customDeformerWeight root) for
/// one or more mesh shapes on the same deformer. Multi-shape safe: writes
/// all <shape> blocks first, then all <weights> blocks, mirroring
/// deformer.py's _export_deformer_weight_xml layout. Every input list must
/// have the same length (one entry per shape).
#[pyfunction]
#[pyo3(signature = (
    path, file_name, deformer_name,
    shape_names, world_matrices, positions_list,
    polygon_counts_list, polygon_connects_list, weights_list,
))]
#[allow(clippy::too_many_arguments)]
pub fn write_deformer_weight_xml(
    path: String,
    file_name: String,
    deformer_name: String,
    shape_names: Vec<String>,
    world_matrices: Vec<Vec<f64>>,
    positions_list: Vec<Vec<f64>>,
    polygon_counts_list: Vec<Vec<usize>>,
    polygon_connects_list: Vec<Vec<usize>>,
    weights_list: Vec<Vec<f64>>,
) -> PyResult<()> {
    let num_shapes = shape_names.len();
    if world_matrices.len() != num_shapes
        || positions_list.len() != num_shapes
        || polygon_counts_list.len() != num_shapes
        || polygon_connects_list.len() != num_shapes
        || weights_list.len() != num_shapes
    {
        return Err(PyValueError::new_err(
            "shape_names, world_matrices, positions_list, polygon_counts_list, \
             polygon_connects_list, and weights_list must all have the same length",
        ));
    }

    let file = std::fs::File::create(&path).map_err(io_err)?;
    let mut out = std::io::BufWriter::new(file);

    writeln!(out, "<?xml version=\"1.0\" encoding=\"utf-8\"?>").map_err(io_err)?;
    writeln!(out, "<customDeformerWeight>").map_err(io_err)?;
    writeln!(out, "    <headerInfo fileName=\"{}\"/>", escape_attr(&file_name))
        .map_err(io_err)?;

    for i in 0..num_shapes {
        let shape_name = &shape_names[i];
        let world_matrix = &world_matrices[i];
        let positions = &positions_list[i];
        let polygon_counts = &polygon_counts_list[i];
        let polygon_connects = &polygon_connects_list[i];

        if positions.len() % 3 != 0 {
            return Err(PyValueError::new_err(format!(
                "positions for shape '{shape_name}' must have a length multiple of 3"
            )));
        }
        let num_verts = positions.len() / 3;

        writeln!(
            out,
            "    <shape name=\"{}\" stride=\"3\" size=\"{}\" max=\"{}\" worldMatrix=\"{}\">",
            escape_attr(shape_name),
            num_verts,
            num_verts,
            join_floats_no_trailing_space(world_matrix),
        )
        .map_err(io_err)?;

        for vert in 0..num_verts {
            let x = positions[vert * 3];
            let y = positions[vert * 3 + 1];
            let z = positions[vert * 3 + 2];
            writeln!(
                out,
                "        <point index=\"{vert}\" value=\"{x:.6} {y:.6} {z:.6}\"/>",
            )
            .map_err(io_err)?;
        }

        writeln!(
            out,
            "        <polygonCounts size=\"{}\" polygonCounts=\"{}\"/>",
            polygon_counts.len(),
            join_usizes_no_trailing_space(polygon_counts),
        )
        .map_err(io_err)?;

        writeln!(
            out,
            "        <polygonConnects polygonConnects=\"{}\" size=\"{}\"/>",
            join_usizes_no_trailing_space(polygon_connects),
            polygon_connects.len(),
        )
        .map_err(io_err)?;

        writeln!(out, "    </shape>").map_err(io_err)?;
    }

    for i in 0..num_shapes {
        let shape_name = &shape_names[i];
        let weights = &weights_list[i];
        let num_verts = weights.len();

        writeln!(
            out,
            "    <weights deformer=\"{}\" source=\"baseLayer\" shape=\"{}\" layer=\"0\" defaultValue=\"-1.000000\" size=\"{}\" max=\"{}\">",
            escape_attr(&deformer_name),
            escape_attr(shape_name),
            num_verts,
            num_verts,
        )
        .map_err(io_err)?;

        for (vert, weight) in weights.iter().enumerate() {
            writeln!(out, "        <point index=\"{vert}\" value=\"{weight:.6}\"/>")
                .map_err(io_err)?;
        }

        writeln!(out, "    </weights>").map_err(io_err)?;
    }

    writeln!(out, "</customDeformerWeight>").map_err(io_err)?;
    out.flush().map_err(io_err)?;
    Ok(())
}

#[cfg(test)]
#[path = "deformer_xml_tests.rs"]
mod tests;
