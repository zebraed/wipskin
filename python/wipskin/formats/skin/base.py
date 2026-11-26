"""Contract every skin weight format implements."""

from __future__ import annotations

import abc
import enum
import os
from dataclasses import dataclass, field

from wipskin.core import weight_files


@dataclass
class ViewerInfo:
    """What the viewer shows for one weight file (see SkinWeightFormat.describe).

    Attributes:
        meta_lines (list): Summary lines for the metadata box.
        influences (list): Influence names for the list; names missing from
            the scene are dimmed and double-click selects the others.
    """

    meta_lines: list = field(default_factory=list)
    influences: list = field(default_factory=list)


@dataclass
class SkinWeightData:
    """Skin weights of one shape, as a format's reader/writer exchanges them.

    Dense and vertex-major, the layout MFnSkinCluster.getWeights/setWeights
    use: the weight of influence i on vertex v is
    ``weights[v * len(influences) + i]``.

    Attributes:
        shape (str): Name the weights were exported from; Import "saved
            shape" looks it up in the scene.
        influences (list): Influence (joint) names, in column order.
        weights (list): Flat weights, len == vertex_count * len(influences).

    Raises:
        ValueError: When influences is empty or repeats a name, or weights
            does not fill whole vertex rows.
    """

    shape: str
    influences: list
    weights: list

    def __post_init__(self):
        self.influences = list(self.influences)
        self.weights = [float(value) for value in self.weights]
        if not self.influences:
            raise ValueError(f"{self.shape}: skin weights need an influence.")

        if len(set(self.influences)) != len(self.influences):
            raise ValueError(f"{self.shape}: influence names repeat.")

        if len(self.weights) % len(self.influences):
            raise ValueError(
                f"{self.shape}: {len(self.weights)} weights do not fill rows "
                f"of {len(self.influences)} influences."
            )

    @property
    def vertex_count(self) -> int:
        """Number of vertex rows."""
        return len(self.weights) // len(self.influences)

    @classmethod
    def from_vertex_weights(cls, shape, vertex_weights, influences=None):
        """Build from one ``{influence: weight}`` dict per vertex.

        Args:
            shape (str): Recorded shape name.
            vertex_weights (list): Dict per vertex, in vertex order; missing
                influences weigh 0.
            influences (list, optional): Column order; first-seen order of
                the dicts' keys when omitted.

        Returns:
            SkinWeightData: The dense equivalent.
        """
        if influences is None:
            influences = []
            for row in vertex_weights:
                for name in row:
                    if name not in influences:
                        influences.append(name)

        weights = []
        for row in vertex_weights:
            weights.extend(float(row.get(name, 0.0)) for name in influences)
        return cls(shape=shape, influences=influences, weights=weights)

    def build_column_matrix(self, columns, column_count) -> list:
        """Weights laid out for another influence order (e.g. a skinCluster's).

        Args:
            columns (list): Target column of each of self.influences.
            column_count (int): Width of the target rows; columns no
                influence maps to stay 0.

        Returns:
            list: Flat vertex-major weights, vertex_count * column_count.

        Raises:
            ValueError: When columns does not give one valid, distinct
                column per influence.
        """
        if len(columns) != len(self.influences):
            raise ValueError(
                f"{len(columns)} columns for {len(self.influences)} influences."
            )

        if len(set(columns)) != len(columns) or any(
            not 0 <= column < column_count for column in columns
        ):
            raise ValueError(
                f"Columns must be distinct and within 0..{column_count - 1}."
            )

        source_count = len(self.influences)
        matrix = [0.0] * (self.vertex_count * column_count)
        for vertex in range(self.vertex_count):
            source = vertex * source_count
            target = vertex * column_count
            for index, column in enumerate(columns):
                matrix[target + column] = self.weights[source + index]
        return matrix

    def list_vertex_weights(self) -> list:
        """One ``{influence: weight}`` dict per vertex, zero weights left out."""
        count = len(self.influences)
        rows = []
        for start in range(0, len(self.weights), count):
            row = self.weights[start:start + count]
            rows.append({
                name: weight
                for name, weight in zip(self.influences, row)
                if weight
            })
        return rows


class Availability(enum.Enum):
    """Whether a format can run in the current session, and if not, why."""

    AVAILABLE = "available"
    #: The format's own package is absent: a normal setup, not worth a warning.
    NOT_INSTALLED = "not_installed"
    #: Installed, but something it needs is missing: worth telling the user.
    MISSING_DEPENDENCY = "missing_dependency"


class SkinWeightFormat(abc.ABC):
    """What a skin weight format owns on disk and how to recognize it.

    Only mode, label and extensions are required: that alone lists, versions,
    renames and comments the format's files. Everything else has a default.
    """

    mode = ""
    label = ""
    extensions = ()
    #: Viewer group title; "<label> Viewer" when left empty.
    viewer_title = ""
    #: Settings key of the Export "Auto Naming" checkbox. When left empty a
    #: per-mode key is generated and given a False default.
    export_auto_naming_setting = ""
    #: Sidecar "format" value this format's files get; the mode when empty.
    metadata_format = ""
    #: Viewer chrome for formats with has_chunk_selector.
    viewer_selector_label = "Item:"
    viewer_selector_tooltip = ""
    viewer_print_tooltip = ""
    #: Tooltip of the viewer's metadata box.
    viewer_meta_tooltip = "Summary metadata for the selected weight file."
    is_text_format = False
    supports_temp_file = False
    #: Files hold several chunks the viewer offers in a selector combo.
    has_chunk_selector = False
    #: Narrower than is_text_format: mGear files are text too, but the
    #: "Generate Opposite Side..." entry is deliberately XML-only.
    supports_opposite_side = False
    #: Extensions whose files list other weight files instead of holding
    #: weights themselves, so the file list can tint them.
    pack_extensions = ()
    #: Which format the tab lands on when the saved one cannot run: the
    #: available format with the lowest rank wins.
    fallback_rank = 100

    #: True when export_auto_naming_setting was generated, so its default
    #: is declared on the format's behalf (see get_declared_defaults).
    generated_auto_naming_setting = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name in ("mode", "label", "extensions"):
            if not getattr(cls, name, None):
                raise TypeError(f"{cls.__name__} must define {name!r}")

        if not cls.viewer_title:
            cls.viewer_title = f"{cls.label} Viewer"

        if not cls.metadata_format:
            cls.metadata_format = cls.mode

        if not cls.export_auto_naming_setting:
            cls.export_auto_naming_setting = (
                f"setting_wipskin_{cls.mode}_exportAutoNaming"
            )
            cls.generated_auto_naming_setting = True

    def describe(self, path):
        """What the viewer shows for path; override to fill it.

        Called by the default viewer flow (formats without their own
        SkinFormatIO). Raise OSError/ValueError for unreadable files; the
        viewer shows the message.

        Args:
            path (str): Weight file path.

        Returns:
            ViewerInfo: A summary of read_weights() when the format has a
            reader; otherwise empty, so the viewer shows the file header and
            sidecar audit only.
        """
        if not self.has_weight_reader():
            return ViewerInfo()

        data = self.read_weights(path)
        return ViewerInfo(
            meta_lines=[
                f"Shape: {data.shape}",
                f"Vertices: {data.vertex_count}",
                f"Influences: {len(data.influences)}",
            ],
            influences=list(data.influences),
        )

    def read_weights(self, path):
        """Read the skin weights one file holds; override to enable Import.

        With the default adapter, overriding this turns on Import: the shared
        engine applies the result to the scene.

        Args:
            path (str): Weight file path.

        Returns:
            SkinWeightData: The file's weights.

        Raises:
            OSError, ValueError: When the file cannot be read.
        """
        raise NotImplementedError(f"{self.label} has no weight reader.")

    def write_weights(self, path, data):
        """Write one shape's skin weights; override to enable Export.

        With the default adapter, overriding this turns on Export: the shared
        engine collects data from the scene and calls this once per shape.

        Args:
            path (str): File to write (its directory exists).
            data (SkinWeightData): Weights to store.

        Raises:
            OSError, ValueError: When the file cannot be written.
        """
        raise NotImplementedError(f"{self.label} has no weight writer.")

    @classmethod
    def has_weight_reader(cls) -> bool:
        """True when this format overrides read_weights."""
        return cls.read_weights is not SkinWeightFormat.read_weights

    @classmethod
    def has_weight_writer(cls) -> bool:
        """True when this format overrides write_weights."""
        return cls.write_weights is not SkinWeightFormat.write_weights

    @classmethod
    def get_availability(cls) -> Availability:
        """Whether this format can run in the current session."""
        return Availability.AVAILABLE

    @classmethod
    def is_available(cls) -> bool:
        """True when this format can run in the current session."""
        return cls.get_availability() is Availability.AVAILABLE

    @classmethod
    def get_unavailable_reason(cls) -> str:
        """Why this format is unusable, for a disabled control's tooltip."""
        return ""

    def get_primary_extension(self) -> str:
        """Extension used when a name is typed without one."""
        return self.extensions[0]

    def get_metadata_format(self, path) -> str:
        """Sidecar "format" value for one of this format's files.

        Override when some files of the format record a different value.

        Args:
            path (str): Weight file path or Files-list name.

        Returns:
            str: Value stored in the sidecar's "format" field.
        """
        return self.metadata_format

    def get_temp_file_path(self):
        """Fixed file the Export Temp / Import Temp buttons use.

        Returns:
            str | None: The path for formats with supports_temp_file; None
            for the rest.
        """
        return None

    def get_default_settings(self) -> dict:
        """Default value per settings key this format's UI reads.

        Keys must not collide with another format's or with the built-in
        ones; the values are stored as-is, so keep QSettings key spellings
        stable once shipped.
        """
        return {}

    def is_pack_filename(self, name) -> bool:
        """True when name carries one of this format's pack extensions."""
        ext = os.path.splitext(str(name))[1].lstrip(".").lower()
        return ext in {value.lower() for value in self.pack_extensions}

    def get_file_predicate(self):
        """Optional path filter for list_files, or None to accept any."""
        return None

    def influence_node_types(self):
        """Node types this format's influences resolve to; None accepts any."""
        return None

    def can_rename_influence(self, name) -> bool:
        """True when an influence name can be rewritten inside this file.

        Per file rather than per format: mGear writes .jSkin as JSON but
        .gSkin as a binary pickle, so only some of its files qualify.
        """
        return False

    def expand_file_names(self, directory, names) -> list:
        """File names Archive and Delete should act on for a selection.

        Lets one list entry stand for the whole set it owns; the default
        acts on the selection as-is.

        Args:
            directory (str): Weight directory holding names.
            names (list): Files-list names of the selected entries.

        Returns:
            list: Files-list names to act on.
        """
        return list(names)

    def list_files(self, directory) -> list:
        """Weight file names this format owns in directory."""
        return weight_files.scan_weight_files(
            directory,
            [ext.lower() for ext in self.extensions],
            predicate=self.get_file_predicate(),
        )


def select_available_format(skin_formats, saved_mode):
    """Pick the format the tab should start on.

    Args:
        skin_formats (iterable): SkinWeightFormat instances.
        saved_mode (str): Mode stored in the user's settings; may be empty or
            name a format that is no longer registered.

    Returns:
        SkinWeightFormat: The saved format when it can run, else the
        available one with the lowest fallback_rank.

    Raises:
        ValueError: When no format can run.
    """
    skin_formats = list(skin_formats)
    for skin_format in skin_formats:
        if skin_format.mode == saved_mode and skin_format.is_available():
            return skin_format

    available = [
        skin_format for skin_format in skin_formats
        if skin_format.is_available()
    ]
    if not available:
        raise ValueError("No skin weight format can run in this session.")

    return min(available, key=lambda skin_format: skin_format.fallback_rank)


def get_declared_defaults(skin_format) -> dict:
    """Settings defaults skin_format declares, including generated ones.

    Args:
        skin_format (SkinWeightFormat): Format to read.

    Returns:
        dict: get_default_settings() plus a False default for a generated
        export_auto_naming_setting.
    """
    defaults = dict(skin_format.get_default_settings())
    if skin_format.generated_auto_naming_setting:
        defaults.setdefault(skin_format.export_auto_naming_setting, False)

    return defaults


def merge_default_settings(skin_formats):
    """Combine every format's declared default settings.

    Args:
        skin_formats (iterable): SkinWeightFormat instances.

    Returns:
        dict: Settings key -> default value.

    Raises:
        ValueError: When two formats declare the same key.
    """
    merged = {}
    owners = {}
    for skin_format in skin_formats:
        for key, value in get_declared_defaults(skin_format).items():
            if key in merged:
                raise ValueError(
                    f"Settings key {key!r} is declared by both "
                    f"{owners[key]!r} and {skin_format.mode!r}."
                )

            merged[key] = value
            owners[key] = skin_format.mode
    return merged


def check_can_register(registered_formats, new_format, reserved_setting_keys):
    """Raise when new_format cannot join the already registered formats.

    Nothing is registered here; callers register only once this passes, so a
    rejected format leaves no partial state behind.

    Args:
        registered_formats (iterable): SkinWeightFormat instances already
            registered.
        new_format (SkinWeightFormat): The format to add.
        reserved_setting_keys (iterable): Settings keys that already have a
            built-in default (constants.REQUESTED_DEFAULTS).

    Raises:
        TypeError: When new_format is not a SkinWeightFormat instance.
        ValueError: When its mode is taken, one of its settings keys is
            already declared, or its auto naming key has no default.
    """
    if not isinstance(new_format, SkinWeightFormat):
        raise TypeError(
            f"Expected a SkinWeightFormat instance, got {new_format!r}."
        )

    registered_formats = list(registered_formats)
    for skin_format in registered_formats:
        if skin_format.mode == new_format.mode:
            raise ValueError(
                f"Skin format mode {new_format.mode!r} is already registered "
                f"by {type(skin_format).__name__}."
            )

    reserved_setting_keys = set(reserved_setting_keys)
    # Raises on a key clash between the new format and a registered one.
    format_keys = set(
        merge_default_settings([*registered_formats, new_format])
    )
    new_keys = set(get_declared_defaults(new_format))
    clashing = sorted(new_keys & reserved_setting_keys)
    if clashing:
        raise ValueError(
            f"{new_format.mode!r} redeclares built-in settings keys: "
            f"{clashing}"
        )

    auto_naming_key = new_format.export_auto_naming_setting
    if auto_naming_key not in reserved_setting_keys | format_keys:
        raise ValueError(
            f"{new_format.mode!r} has no default for its auto naming key "
            f"{auto_naming_key!r}: declare it in get_default_settings()."
        )
