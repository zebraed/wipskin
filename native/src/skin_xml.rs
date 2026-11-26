//! Skin (skinCluster) deformerWeights XML: native counterparts of
//! xml_skin.py's _build_weight_matrix_from_xml (read) and the export path
//! that used to go through cmds.deformerWeights(export=True) (write).

use crate::xml_common::{escape_attr, io_err};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use quick_xml::events::{BytesStart, Event};
use quick_xml::reader::Reader;
use std::collections::HashMap;
use std::io::Write as _;

/// Build a dense skin weight matrix from a Maya `deformerWeights` XML file.
///
/// Streams the XML once (no DOM is built) and fills a flat, row-major matrix of
/// shape `num_verts * scene_influences.len()`. Element `(vertex, influence)` is
/// stored at index `vertex * scene_influences.len() + influence`.
///
/// Each `<weights source="...">` block maps to the column of the matching entry
/// in `scene_influences`, and every `<point index="i" value="w"/>` inside it
/// writes `w` to row `i` of that column. Columns therefore follow
/// `scene_influences` order, not the order the blocks appear in the file.
///
/// # Arguments
/// * `path` - Path to the `deformerWeights` XML file to read.
/// * `scene_influences` - Influence (joint) names in the desired column order.
///   A `<weights>` block whose `source` is not in this list is skipped, so this
///   doubles as a filter for unrelated influences.
/// * `num_verts` - Number of vertices, i.e. the number of rows in the matrix.
///
/// # Returns
/// A `Vec<f64>` of length `num_verts * scene_influences.len()`. Entries with no
/// corresponding `<point>` default to `0.0`.
///
/// # Errors
/// * `PyIOError` if the file cannot be opened.
/// * `PyValueError` if the XML is malformed or an attribute cannot be decoded.
///
/// # Notes
/// * Points whose `index` is out of range (`>= num_verts`), or whose `index` /
///   `value` cannot be parsed, are silently skipped (matches the Python
///   original's behavior).
/// * Mixed-deformer ownership filtering is not yet replicated (see
///   `xml_skin.py`'s `_list_skin_weights_elements`). Filtering by
///   `scene_influences` already excludes unrelated blocks in the common case
///   where deformers do not share influence names.
// スキンXMLを1回のストリーミングで走査し、行=頂点列=インフルエンスの
// row-majorウェイト行列を組み立てる。列順はscene_influencesに従い
// 一致しない<weights>ブロックは無視する
#[pyfunction]
pub fn build_weight_matrix(
    path: String,
    scene_influences: Vec<String>,
    num_verts: usize,
) -> PyResult<Vec<f64>> {
    let num_inf = scene_influences.len();
    let mut inf_column: HashMap<&str, usize> = HashMap::with_capacity(num_inf);
    for (i, name) in scene_influences.iter().enumerate() {
        inf_column.insert(name.as_str(), i);
    }

    let mut matrix: Vec<f64> = vec![0.0f64; num_verts * num_inf];

    let mut reader = Reader::from_file(&path).map_err(io_err)?;
    let mut buf = Vec::new();
    let mut current_column: Option<usize> = None;

    loop {
        let event = match reader.read_event_into(&mut buf) {
            Ok(event) => event,
            Err(e) => return Err(PyValueError::new_err(e.to_string())),
        };

        match event {
            Event::Eof => break,
            Event::Start(e) => {
                if e.name().as_ref() == b"weights" {
                    // read the source column
                    current_column = read_weights_source_column(&e, &inf_column)?;
                }
            }
            Event::End(e) => {
                if e.name().as_ref() == b"weights" {
                    // set the current column to None
                    current_column = None;
                }
            }
            Event::Empty(e) => {
                if e.name().as_ref() == b"point" {
                    // apply the point to the matrix
                    if let Some(column) = current_column {
                        apply_point(&e, column, num_inf, num_verts, &mut matrix)?;
                    }
                }
            }
            _ => {}
        }
        buf.clear();
    }

    Ok(matrix)
}

fn read_weights_source_column(
    e: &BytesStart,
    inf_column: &HashMap<&str, usize>,
) -> PyResult<Option<usize>> {
    for attr in e.attributes() {
        let attr = attr.map_err(|err| PyValueError::new_err(err.to_string()))?;
        if attr.key.as_ref() != b"source" {
            continue;
        }
        // Prefer unescape_value over normalized_value until XmlVersion wiring is clear.
        let value = attr
            .unescape_value()
            .map_err(|err| PyValueError::new_err(err.to_string()))?;
        return Ok(inf_column.get(value.as_ref()).copied());
    }
    Ok(None)
}

fn apply_point(
    e: &BytesStart,
    column: usize,
    num_inf: usize,
    num_verts: usize,
    matrix: &mut [f64],
) -> PyResult<()> {
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
            matrix[row * num_inf + column] = value;
        }
    }
    Ok(())
}

// Maya deformerWeights writes a trailing space after the last matrix value.
fn format_world_matrix(values: &[f64]) -> String {
    let mut out = String::with_capacity(values.len() * 11);
    for value in values {
        out.push_str(&format!("{value:.6} "));
    }
    out
}

// Same trailing-space convention as Maya's polygonCounts/polygonConnects.
fn join_with_trailing_space(values: &[usize]) -> String {
    let mut out = String::with_capacity(values.len() * 3);
    for value in values {
        out.push_str(&value.to_string());
        out.push(' ');
    }
    out
}

/// Stream a single-mesh skinCluster deformerWeights XML to disk.
/// Matches Maya export quirks: no encoding on the declaration, trailing
/// spaces in matrix/poly attrs, leading space in shape point values,
/// sparse weights (omit |w| <= tolerance), layer = influence column index.
#[pyfunction]
#[pyo3(signature = (
    path, file_name, world_matrix, deformer_name, deformer_type,
    attributes, shape_name, group, positions, influence_names,
    weight_matrix, default_value, tolerance,
    polygon_counts=Vec::new(), polygon_connects=Vec::new(),
))]
#[allow(clippy::too_many_arguments)]
pub fn write_skin_xml(
    path: String,
    file_name: String,
    world_matrix: Vec<f64>,
    deformer_name: String,
    deformer_type: String,
    attributes: Vec<(String, String, String)>,
    shape_name: String,
    group: usize,
    positions: Vec<f64>,
    influence_names: Vec<String>,
    weight_matrix: Vec<f64>,
    default_value: f64,
    tolerance: f64,
    polygon_counts: Vec<usize>,
    polygon_connects: Vec<usize>,
) -> PyResult<()> {
    if positions.len() % 3 != 0 {
        return Err(PyValueError::new_err(
            "positions length must be a multiple of 3",
        ));
    }
    let num_verts = positions.len() / 3;
    let num_inf = influence_names.len();
    if num_inf > 0 && weight_matrix.len() != num_verts * num_inf {
        return Err(PyValueError::new_err(
            "weight_matrix length must equal num_verts * len(influence_names)",
        ));
    }

    let file = std::fs::File::create(&path).map_err(io_err)?;
    let mut out = std::io::BufWriter::new(file);

    writeln!(out, "<?xml version=\"1.0\"?>").map_err(io_err)?;
    writeln!(out, "<deformerWeight>").map_err(io_err)?;
    writeln!(
        out,
        "  <headerInfo fileName=\"{}\" worldMatrix=\"{}\"/>",
        escape_attr(&file_name),
        format_world_matrix(&world_matrix),
    )
    .map_err(io_err)?;

    writeln!(
        out,
        "  <deformer name=\"{}\" type=\"{}\">",
        escape_attr(&deformer_name),
        escape_attr(&deformer_type),
    )
    .map_err(io_err)?;
    for (name, attr_type, value) in &attributes {
        writeln!(
            out,
            "    <attribute name=\"{}\" type=\"{}\" value=\"{}\"/>",
            escape_attr(name),
            escape_attr(attr_type),
            escape_attr(value),
        )
        .map_err(io_err)?;
    }
    writeln!(out, "  </deformer>").map_err(io_err)?;

    writeln!(
        out,
        "  <shape name=\"{}\" group=\"{}\" stride=\"3\" size=\"{}\" max=\"{}\">",
        escape_attr(&shape_name),
        group,
        num_verts,
        num_verts.saturating_sub(1),
    )
    .map_err(io_err)?;
    for vert in 0..num_verts {
        let x = positions[vert * 3];
        let y = positions[vert * 3 + 1];
        let z = positions[vert * 3 + 2];
        writeln!(
            out,
            "    <point index=\"{vert}\" value=\" {x:.6} {y:.6} {z:.6}\"/>",
        )
        .map_err(io_err)?;
    }
    if !polygon_counts.is_empty() {
        let counts_str = join_with_trailing_space(&polygon_counts);
        writeln!(
            out,
            "    <polygonCounts size=\"{}\" polygonCounts=\"{}\"/>",
            polygon_counts.len(),
            counts_str,
        )
        .map_err(io_err)?;
        let connects_str = join_with_trailing_space(&polygon_connects);
        writeln!(
            out,
            "    <polygonConnects size=\"{}\" polygonConnects=\"{}\"/>",
            polygon_connects.len(),
            connects_str,
        )
        .map_err(io_err)?;
    }
    writeln!(out, "  </shape>").map_err(io_err)?;

    for (column, influence_name) in influence_names.iter().enumerate() {
        let mut nonzero: Vec<(usize, f64)> = Vec::new();
        for vert in 0..num_verts {
            let weight = weight_matrix[vert * num_inf + column];
            if weight.abs() > tolerance {
                nonzero.push((vert, weight));
            }
        }
        writeln!(
            out,
            "  <weights deformer=\"{}\" source=\"{}\" shape=\"{}\" layer=\"{}\" defaultValue=\"{:.6}\" size=\"{}\" max=\"{}\">",
            escape_attr(&deformer_name),
            escape_attr(influence_name),
            escape_attr(&shape_name),
            column,
            default_value,
            nonzero.len(),
            num_verts.saturating_sub(1),
        )
        .map_err(io_err)?;
        for (vert, weight) in &nonzero {
            writeln!(out, "    <point index=\"{vert}\" value=\"{weight:.6}\"/>")
                .map_err(io_err)?;
        }
        writeln!(out, "  </weights>").map_err(io_err)?;
    }

    writeln!(out, "</deformerWeight>").map_err(io_err)?;
    out.flush().map_err(io_err)?;
    Ok(())
}

#[cfg(test)]
#[path = "skin_xml_tests.rs"]
mod tests;
