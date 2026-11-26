//! Unit tests for skin_xml.rs. Kept as a sibling file (declared via
//! `#[path = "skin_xml_tests.rs"] mod tests;` in skin_xml.rs) rather than
//! inline, so the source file stays focused on the implementation and
//! `use super::*` still gives these tests access to skin_xml's private
//! items.

use super::*;

fn start_tag(name: &str, attrs: &[(&str, &str)]) -> BytesStart<'static> {
    let mut tag = BytesStart::new(name.to_string());
    for (key, value) in attrs {
        tag.push_attribute((*key, *value));
    }
    tag
}

#[test]
fn format_world_matrix_uses_six_decimals_with_a_trailing_space() {
    assert_eq!(format_world_matrix(&[1.0, 0.0]), "1.000000 0.000000 ");
}

#[test]
fn join_with_trailing_space_appends_a_space_after_every_value() {
    assert_eq!(join_with_trailing_space(&[3, 4]), "3 4 ");
}

#[test]
fn join_with_trailing_space_handles_empty_input() {
    assert_eq!(join_with_trailing_space(&[]), "");
}

#[test]
fn read_weights_source_column_maps_a_known_influence() {
    let mut inf_column: HashMap<&str, usize> = HashMap::new();
    inf_column.insert("joint1", 0);
    inf_column.insert("joint2", 1);
    let tag = start_tag("weights", &[("source", "joint2")]);
    assert_eq!(
        read_weights_source_column(&tag, &inf_column).unwrap(),
        Some(1),
    );
}

#[test]
fn read_weights_source_column_is_none_for_an_unknown_influence() {
    let inf_column: HashMap<&str, usize> = HashMap::new();
    let tag = start_tag("weights", &[("source", "joint99")]);
    assert_eq!(
        read_weights_source_column(&tag, &inf_column).unwrap(),
        None,
    );
}

#[test]
fn read_weights_source_column_is_none_when_source_attribute_is_missing() {
    let inf_column: HashMap<&str, usize> = HashMap::new();
    let tag = start_tag("weights", &[("shape", "pPlaneShape1")]);
    assert_eq!(
        read_weights_source_column(&tag, &inf_column).unwrap(),
        None,
    );
}

#[test]
fn apply_point_writes_into_the_right_matrix_cell() {
    let num_inf = 3;
    let num_verts = 2;
    let mut matrix = vec![0.0f64; num_verts * num_inf];
    let tag = start_tag("point", &[("index", "1"), ("value", "0.75")]);
    apply_point(&tag, 2, num_inf, num_verts, &mut matrix).unwrap();
    // Row 1, column 2 -> flat index 1*3 + 2 = 5.
    assert_eq!(matrix, vec![0.0, 0.0, 0.0, 0.0, 0.0, 0.75]);
}

#[test]
fn apply_point_ignores_an_out_of_range_row() {
    let num_inf = 2;
    let num_verts = 1;
    let mut matrix = vec![0.0f64; num_verts * num_inf];
    let tag = start_tag("point", &[("index", "9"), ("value", "1.0")]);
    // Must not panic on an out-of-bounds row.
    apply_point(&tag, 0, num_inf, num_verts, &mut matrix).unwrap();
    assert_eq!(matrix, vec![0.0, 0.0]);
}

struct TempDir(std::path::PathBuf);

impl TempDir {
    fn new(label: &str) -> Self {
        let dir = std::env::temp_dir().join(format!(
            "wipskin_native_test_skin_{label}_{}_{:?}",
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
fn write_then_read_round_trips_a_dense_weight_matrix() {
    let dir = TempDir::new("round_trip");
    let path = dir.0.join("skinCluster1.xml");

    let influence_names = vec!["joint1".to_string(), "joint2".to_string()];
    // 3 verts x 2 influences, row-major.
    let weight_matrix = vec![
        1.0, 0.0, // vert 0
        0.5, 0.5, // vert 1
        0.0, 1.0, // vert 2
    ];

    write_skin_xml(
        path.to_string_lossy().into_owned(),
        "skinCluster1.xml".to_string(),
        vec![0.0; 16],
        "skinCluster1".to_string(),
        "skinCluster".to_string(),
        vec![],
        "pPlaneShape1".to_string(),
        0,
        vec![0.0; 9], // 3 verts x 3 (positions, unrelated to weights)
        influence_names.clone(),
        weight_matrix.clone(),
        0.0,
        1e-6,
        Vec::new(),
        Vec::new(),
    )
    .unwrap();

    let read_back = build_weight_matrix(
        path.to_string_lossy().into_owned(),
        influence_names,
        3,
    )
    .unwrap();

    assert_eq!(read_back, weight_matrix);
}

#[test]
fn build_weight_matrix_columns_follow_the_caller_order_not_the_file_order() {
    let dir = TempDir::new("column_order");
    let path = dir.0.join("skinCluster1.xml");

    // File is written with joint1 in column 0, joint2 in column 1.
    write_skin_xml(
        path.to_string_lossy().into_owned(),
        "skinCluster1.xml".to_string(),
        vec![0.0; 16],
        "skinCluster1".to_string(),
        "skinCluster".to_string(),
        vec![],
        "pPlaneShape1".to_string(),
        0,
        vec![0.0; 3],
        vec!["joint1".to_string(), "joint2".to_string()],
        vec![0.25, 0.75], // 1 vert: joint1=0.25, joint2=0.75
        0.0,
        1e-6,
        Vec::new(),
        Vec::new(),
    )
    .unwrap();

    // Read back with the influence order reversed.
    let read_back = build_weight_matrix(
        path.to_string_lossy().into_owned(),
        vec!["joint2".to_string(), "joint1".to_string()],
        1,
    )
    .unwrap();

    assert_eq!(read_back, vec![0.75, 0.25]);
}

#[test]
fn write_skin_xml_rejects_a_weight_matrix_of_the_wrong_length() {
    let result = write_skin_xml(
        "unused.xml".to_string(),
        "unused.xml".to_string(),
        vec![0.0; 16],
        "skinCluster1".to_string(),
        "skinCluster".to_string(),
        vec![],
        "pPlaneShape1".to_string(),
        0,
        vec![0.0; 3], // 1 vert
        vec!["joint1".to_string(), "joint2".to_string()],
        vec![1.0], // should be 1 vert x 2 influences = 2 values
        0.0,
        1e-6,
        Vec::new(),
        Vec::new(),
    );
    assert!(result.is_err());
}
