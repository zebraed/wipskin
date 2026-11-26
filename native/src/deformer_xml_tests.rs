//! Unit tests for deformer_xml.rs. Kept as a sibling file (declared via
//! `#[path = "deformer_xml_tests.rs"] mod tests;` in deformer_xml.rs)
//! rather than inline, so the source file stays focused on the
//! implementation and `use super::*` still gives these tests access to
//! deformer_xml's private items.

use super::*;

fn start_tag(name: &str, attrs: &[(&str, &str)]) -> BytesStart<'static> {
    let mut tag = BytesStart::new(name.to_string());
    for (key, value) in attrs {
        tag.push_attribute((*key, *value));
    }
    tag
}

#[test]
fn join_floats_no_trailing_space_formats_six_decimals_space_separated() {
    assert_eq!(
        join_floats_no_trailing_space(&[1.0, 2.5, -3.0]),
        "1.000000 2.500000 -3.000000",
    );
}

#[test]
fn join_floats_no_trailing_space_handles_empty_input() {
    assert_eq!(join_floats_no_trailing_space(&[]), "");
}

#[test]
fn join_usizes_no_trailing_space_joins_with_single_spaces() {
    assert_eq!(join_usizes_no_trailing_space(&[0, 1, 2]), "0 1 2");
}

#[test]
fn weights_shape_matches_true_for_matching_shape_attribute() {
    let tag = start_tag("weights", &[("shape", "pSphereShape1")]);
    assert!(weights_shape_matches(&tag, "pSphereShape1").unwrap());
}

#[test]
fn weights_shape_matches_false_for_a_different_shape() {
    let tag = start_tag("weights", &[("shape", "pCubeShape1")]);
    assert!(!weights_shape_matches(&tag, "pSphereShape1").unwrap());
}

#[test]
fn weights_shape_matches_false_when_shape_attribute_is_missing() {
    let tag = start_tag("weights", &[("deformer", "cluster1")]);
    assert!(!weights_shape_matches(&tag, "pSphereShape1").unwrap());
}

#[test]
fn apply_deformer_point_writes_the_value_at_its_index() {
    let mut weights = vec![1.0f64; 4];
    let tag = start_tag("point", &[("index", "2"), ("value", "0.500000")]);
    apply_deformer_point(&tag, 4, &mut weights).unwrap();
    assert_eq!(weights, vec![1.0, 1.0, 0.5, 1.0]);
}

#[test]
fn apply_deformer_point_ignores_an_out_of_range_index() {
    let mut weights = vec![1.0f64; 2];
    let tag = start_tag("point", &[("index", "5"), ("value", "0.9")]);
    // Must not panic on an out-of-bounds index -- a corrupted/foreign
    // file shouldn't crash the reader.
    apply_deformer_point(&tag, 2, &mut weights).unwrap();
    assert_eq!(weights, vec![1.0, 1.0]);
}

struct TempDir(std::path::PathBuf);

impl TempDir {
    fn new(label: &str) -> Self {
        let dir = std::env::temp_dir().join(format!(
            "wipskin_native_test_{label}_{}_{:?}",
            std::process::id(),
            std::thread::current().id(),
        ));
        std::fs::create_dir_all(&dir).unwrap();
        Self(dir)
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

#[test]
fn write_then_read_round_trips_single_shape_weights() {
    let dir = TempDir::new("round_trip");
    let path = dir.0.join("cluster1.xml");

    let identity = vec![
        1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0,
    ];
    let positions = vec![0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0];
    let weights = vec![0.25, 0.5, 0.75];

    write_deformer_weight_xml(
        path.to_string_lossy().into_owned(),
        "cluster1.xml".to_string(),
        "cluster1".to_string(),
        vec!["pPlaneShape1".to_string()],
        vec![identity],
        vec![positions],
        vec![vec![3]],
        vec![vec![0, 1, 2]],
        vec![weights.clone()],
    )
    .unwrap();

    let read_back = read_deformer_weights(
        path.to_string_lossy().into_owned(),
        "pPlaneShape1".to_string(),
        3,
    )
    .unwrap();

    assert_eq!(read_back, weights);
}

#[test]
fn write_then_read_round_trips_multiple_shapes_without_mixing_them() {
    let dir = TempDir::new("multi_shape");
    let path = dir.0.join("cluster1.xml");
    let identity = vec![0.0; 16];

    write_deformer_weight_xml(
        path.to_string_lossy().into_owned(),
        "cluster1.xml".to_string(),
        "cluster1".to_string(),
        vec!["pSphereShape1".to_string(), "pCubeShape1".to_string()],
        vec![identity.clone(), identity],
        vec![vec![0.0; 6], vec![0.0; 6]],
        vec![vec![], vec![]],
        vec![vec![], vec![]],
        vec![vec![1.0, 0.25], vec![0.5, 0.75]],
    )
    .unwrap();

    let sphere_weights = read_deformer_weights(
        path.to_string_lossy().into_owned(),
        "pSphereShape1".to_string(),
        2,
    )
    .unwrap();
    let cube_weights = read_deformer_weights(
        path.to_string_lossy().into_owned(),
        "pCubeShape1".to_string(),
        2,
    )
    .unwrap();

    assert_eq!(sphere_weights, vec![1.0, 0.25]);
    assert_eq!(cube_weights, vec![0.5, 0.75]);
}

#[test]
fn read_deformer_weights_defaults_to_one_for_an_unknown_shape() {
    let dir = TempDir::new("unknown_shape");
    let path = dir.0.join("cluster1.xml");

    write_deformer_weight_xml(
        path.to_string_lossy().into_owned(),
        "cluster1.xml".to_string(),
        "cluster1".to_string(),
        vec!["pPlaneShape1".to_string()],
        vec![vec![0.0; 16]],
        vec![vec![0.0; 9]],
        vec![vec![3]],
        vec![vec![0, 1, 2]],
        vec![vec![0.1, 0.2, 0.3]],
    )
    .unwrap();

    let read_back = read_deformer_weights(
        path.to_string_lossy().into_owned(),
        "noSuchShape".to_string(),
        3,
    )
    .unwrap();

    assert_eq!(read_back, vec![1.0, 1.0, 1.0]);
}

#[test]
fn write_deformer_weight_xml_rejects_mismatched_list_lengths() {
    let result = write_deformer_weight_xml(
        "unused.xml".to_string(),
        "unused.xml".to_string(),
        "cluster1".to_string(),
        vec!["pSphereShape1".to_string(), "pCubeShape1".to_string()],
        vec![vec![0.0; 16]], // only one matrix for two shapes
        vec![vec![0.0; 3], vec![0.0; 3]],
        vec![vec![], vec![]],
        vec![vec![], vec![]],
        vec![vec![1.0], vec![1.0]],
    );
    assert!(result.is_err());
}
