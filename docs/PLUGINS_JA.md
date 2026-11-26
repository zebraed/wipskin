# WipSkinのスキンウェイト形式プラグインを作る

[English](PLUGINS.md) | 日本語

プラグインを使うと、WipSkin本体を編集せずに、SkinWeightタブへスキンウェイトのファイル形式を追加できます。
同梱のmGearとngSkinToolsも、このガイドで説明するAPIだけで作ったプラグインです（`python/wipskin/plugins/`）。

> 安定性: `wipskin.api.API_VERSION` は `(0, 1)` です。
> メジャーバージョンが0の間、APIは暫定で、マイナーバージョンが上がるときに名前が変わることがあります。
> 新しい機能を使うプラグインは、`API_VERSION` を確認してください。

## 目次

1. [プラグインを読み込む](#1-プラグインを読み込む)
2. [レベル0：ファイルを一覧に出す](#2-レベル0ファイルを一覧に出す)
3. [レベル1：ビューアに内容を出す](#3-レベル1ビューアに内容を出す)
4. [レベル2：読み込みと書き出し](#4-レベル2読み込みと書き出し)
5. [レベル3：独自のフローとオプション](#5-レベル3独自のフローとオプション)
6. [パッケージ構成とimportの規則](#6-パッケージ構成とimportの規則)
7. [プラグインをテストする](#7-プラグインをテストする)
8. [プラグインを翻訳する](#8-プラグインを翻訳する)
9. [形式のリファレンス](#9-形式のリファレンス)

プラグインは、必要なレベルの分だけ書けば動きます。
レベルを1つ上げるには、前のレベルにメソッドをいくつか足します。
書かなかった部分は、WipSkinの既定の動作になります。

| レベル | 書くもの | 得られるもの |
|---|---|---|
| 0 | `mode`、`label`、`extensions` | ファイル一覧、バージョン付きの名前、Rename、Delete、Archive、コメント、ビューアのヘッダー。ImportとExportのボタンは、ツールチップ付きでグレーアウトする |
| 1 | `describe(path)` | ビューアのメタ情報とインフルエンス一覧。シーンに無いインフルエンスは薄く表示し、ダブルクリックで選択できる |
| 2 | `read_weights` と `write_weights` | WipSkin共通のスキンクラスターエンジンによるImportとExport。`describe` を書かなくても、ビューアに要約が出る |
| 3 | `SkinFormatIO`（と `SkinFormatOptions`） | 独自のImport / Exportのフロー、オプションのウィジェット、メニュー、ダイアログ |

レベル2の動くサンプルは [`examples/plugins/wipskin_jsonskin`](../examples/plugins/wipskin_jsonskin) にあります。

## 1. プラグインを読み込む

プラグインは、importされたときに `wipskin.api.register_skin_format()` を呼ぶPythonのモジュールです。
`wipskin.showUI()` は、ウィンドウを開くたびに、環境変数 `WIPSKIN_PLUGINS` に並べたモジュールをimportします。
区切り文字は `PATH` と同じで、Windowsでは `;`、それ以外では `:` です。

```text
PYTHONPATH=<repo>/python;<your plugin folder>
WIPSKIN_PLUGINS=my_studio_skin.plugin
```

- 登録した形式は、次に開いたウィンドウから使えます。
- importに失敗したプラグインは、警告を出して読み飛ばします。
  ほかの形式はそのまま動きます。
- `wipskin.Reload()` は、登録済みのプラグインもWipSkinと一緒にimportし直します。
- 同じ `mode` を2回登録すると `ValueError` になり、どちらも登録されません。

登録した形式は、FormatのコンボボックスでXML、mGear、ngSkinToolsの後ろに並びます。
そのセッションで形式が使えない場合（後述の `get_availability`）、項目はグレーアウトし、形式が返した理由をツールチップに出します。

## 2. レベル0：ファイルを一覧に出す

```python
# my_studio_skin/plugin.py
from wipskin import api


class StudioSkin(api.SkinFormat):
    mode = "studioskin"       # identifier-like; used in settings keys
    label = "Studio Skin"     # shown in the Format combo
    extensions = ("sskin",)   # without the dot


api.register_skin_format(StudioSkin)
```

これだけでプラグインとして動きます。
書かなかった属性には、WipSkinが次の既定値を入れます。

| 属性 | 既定値 |
|---|---|
| `viewer_title` | `"Studio Skin Viewer"` |
| `metadata_format`（サイドカーの `"format"` の値） | `mode` |
| `export_auto_naming_setting` | `setting_wipskin_studioskin_exportAutoNaming`（設定の既定値は `False`） |

## 3. レベル1：ビューアに内容を出す

```python
class StudioSkin(api.SkinFormat):
    ...

    def describe(self, path):
        header = read_my_header(path)   # your parser
        return api.ViewerInfo(
            meta_lines=[f"Mesh: {header.mesh}", f"Vertices: {header.count}"],
            influences=header.joints,
        )
```

読めないファイルに対しては、`OSError` か `ValueError` を送出します。
ビューアは、ファイルの内容の代わりにその例外のメッセージを表示します。

## 4. レベル2：読み込みと書き出し

レベル2で書くのは、ファイルのエンコードとデコードだけです。

```python
class StudioSkin(api.SkinFormat):
    ...

    def read_weights(self, path):
        ...
        return api.SkinWeightData.from_vertex_weights(shape, rows)

    def write_weights(self, path, data):
        for row in data.list_vertex_weights():   # {influence: weight}
            ...
```

### `SkinWeightData`

`SkinWeightData` は、1つのシェイプのウェイトを持ちます。
中身は頂点ごとに並んだ密な配列で、`MFnSkinCluster.getWeights` と `setWeights` と同じ並びです。

| メンバー | 意味 |
|---|---|
| `shape` | ウェイトを書き出した元のシェイプの名前。Importのsaved shapeは、この名前でシーンからシェイプを探す |
| `influences` | インフルエンスの名前。列の順に並ぶ |
| `weights` | 1次元のリスト。頂点 `v` に対するインフルエンス `i` のウェイトは `weights[v * len(influences) + i]` |
| `vertex_count` | 頂点の行数 |
| `from_vertex_weights(shape, rows, influences=None)` | 頂点ごとの `{influence: weight}` の辞書から作る |
| `list_vertex_weights()` | 頂点ごとの `{influence: weight}` の辞書に変換する。ウェイト0は省く |

`SkinWeightData` は、作るときに自分の中身を検証します。
インフルエンスが空のとき、名前が重複しているとき、ウェイトの数が行の幅で割り切れないときは `ValueError` になります。

### コーデックの周りでWipSkinがすること

書き出しでは、選択したスキン付きのメッシュ1つにつき、ファイルを1つ作ります。

- メッシュのスキンクラスターから、ウェイトを `SkinWeightData` に集めます。
- ファイル名はXMLの書き出しと同じ規則で決めます。
  Auto Namingがオンならシェイプ名、オフなら入力したベース名です。
  複数のシェイプを選んだときは、ベース名に `_0001`、`_0002` と番号を付けます。
  version numberがオンなら `.NNNN` も付けます。
- `write_weights` を一時ファイルに対して呼び、成功したときに限り本来のファイルと置き換えます。
  書き込みが途中で失敗しても、途中までのファイルは残りません。
- コメント、ユーザー、シーンを記録したサイドカーを書きます。

読み込みでは、選択したファイルごとに次を行います。

- `read_weights` を呼び、結果を記録されたシェイプへ適用します。
  Import Asがselected shapeのときは、選択している最初のシェイプへ適用します。
- メッシュにスキンクラスターが無ければバインドします。
  既存のスキンクラスターには足りないインフルエンスを追加し、ロックを外します。
  ロックされたインフルエンスへのウェイトの書き込みは無視されるためです。
- インフルエンスはフルパスで対応づけるので、ネームスペースや短い名前の重複があっても取り違えません。
  名前から1つに決まらないときはエラーにします。
- データに無いシーン側のインフルエンスにはウェイト0を入れ、そのあとで正規化します。

対応するのはポリゴンメッシュだけで、頂点は番号で対応づけます。
そのため、メッシュの頂点数がデータの頂点数と一致している必要があります。

## 5. レベル3：独自のフローとオプション

オプションのウィジェット、メニュー、独自のImport / Exportが必要なときは、形式クラスの代わりに `wipskin.api.ui.SkinFormatIO` のサブクラスを登録します。

```python
from wipskin import api
from wipskin.api import ui
from wipskin.api.maya import feedback, scene


class StudioOptions(ui.SkinFormatOptions):
    def build_import_page(self, layout):
        self.mirror_check = ui.QtWidgets.QCheckBox("Mirror on import")
        ui.bind_checkbox(self._settings, "setting_studio_mirror", self.mirror_check)
        layout.addWidget(self.mirror_check)

    def build_export_page(self, layout):
        layout.addStretch()


class StudioSkinIO(ui.SkinFormatIO):
    format_class = StudioSkin
    options_class = StudioOptions

    def import_weights(self, mode):
        paths = self.host.resolve_import_paths(mode)
        if not paths:
            return
        with self.host.undo_chunk("importStudioSkin"):
            ...


api.register_skin_format(StudioSkinIO)
```

オプションが読む設定キーには、形式クラスで既定値を宣言します。

```python
class StudioSkin(api.SkinFormat):
    ...
    def get_default_settings(self):
        return {"setting_studio_mirror": False}
```

### アダプタが使えるもの

アダプタ（`SkinFormatIO` のサブクラス）は、`self.host`（`wipskin.api.ui.Host`）を通してだけタブを操作します。

| 分類 | Hostのメンバー |
|---|---|
| セッション | `settings`、`parent_widget`（ダイアログの親）、`viewer` |
| Files一覧 | `get_directory()`、`refresh_files()`、`select_files(names)`、`list_selected_names()`、`list_selected_paths()` |
| タブのオプション | `import_as_mode()`、`export_auto_naming()`、`export_version_number()`、`get_export_comment()`、`get_export_base_name(names)` |
| ビューア | `get_selected_viewer_file(msg)`、`clear_viewer(msg)`、`set_influence_list_chrome()`、`set_member_list_chrome()`。`viewer.set_header/set_meta/set_list_items/set_list_entries/...` |
| 共通処理 | `resolve_import_paths(mode)`、`undo_chunk(name)`、`exporting_shapes(shapes)`、`is_node_in_scene(name)`、`select_existing_nodes(names, msg)` |

アダプタで上書きできるフックは次のとおりです。
どれも任意で、上書きしなければ既定の動作になります。

| フック | 用途 |
|---|---|
| `update_viewer` | ビューアの表示 |
| `import_weights`、`export_weights` | ImportとExportのボタンの処理 |
| `list_scene_export_shapes`、`get_scene_export_note`、`export_scene_weights` | Filesの右クリックのExport All Skins in Scene...。既定では、対象のシェイプをすべて選択して `export_weights` を1回呼ぶ。選択をまとめて1ファイルにするフローでは、`export_each_shape(shapes)` でシェイプごとに呼ぶ |
| `rename_influence`、`rename_file` | インフルエンス名とファイル名の変更 |
| `list_file_actions` | Filesの右クリックに足す項目 |
| `list_menu_actions` | Optionsメニューに足す項目。拡張点として用意しているが、同梱のプラグインは今のところ使っていない |
| `edit_selected_file` | Filesの項目をダブルクリックしたときの編集 |
| `on_selector_changed`、`print_current_selection` | ビューアの選択行とPrintボタン |

ImportとExportのボタンは、`import_weights` と `export_weights` を上書きすると有効になります。
ボタンを有効にするかどうかを自分で決めるときは、クラスに `supports_import` と `supports_export` を設定します。

レベル3のアダプタでも、`wipskin.api.maya.skin_engine` から、共通のフローと同じ `collect_skin_weights(node)` と `apply_skin_weights(node, data)` を使えます。

## 6. パッケージ構成とimportの規則

同梱のプラグインと同じく、WipSkin本体の層分けにならって構成します。

```
my_studio_skin/
    __init__.py      empty
    plugin.py        entry module: imports ui/adapter (if any) and registers
    constants.py     mode, settings keys, DEFAULT_SETTINGS     ┐ no Qt;
    format.py        your SkinFormat                           │ importable
    weights.py       the only module importing your file library┘ outside Maya
    ui/              (Level 3 only)
        __init__.py
        adapter.py   SkinFormatIO
        options.py   SkinFormatOptions
```

次の規則は、同梱のプラグインとサンプルに対して、WipSkin自身のテストが検査しています。

- WipSkinからimportしてよいのは、`wipskin.api`、`wipskin.api.maya`、`wipskin.api.ui` だけです。
  それ以外は内部の実装で、予告なく変わります。
- Qtに依存するもの（`wipskin.api.ui` とPySide）は `ui/` の中だけに置きます。
  形式とコーデックを、MayaのUIなしでテストできるようにするためです。
- `__init__.py` は空にして、登録は `plugin.py` で行います。
  テストで `format.py` をimportしたときに、形式が登録されないようにするためです。
- 重いライブラリや任意のライブラリは、モジュールのimport時に読み込みません。
  代わりに `get_availability()` を上書きし、`api.Availability.NOT_INSTALLED` か `MISSING_DEPENDENCY` を返します。
  NOT_INSTALLEDは未導入という通常の構成を表し、警告を出しません。
  MISSING_DEPENDENCYは導入されているのに壊れている状態を表し、ウィンドウを開くたびに警告を出します。
  ツールチップに出す理由は `get_unavailable_reason()` で返します。

## 7. プラグインをテストする

`wipskin.api.testing.SkinFormatContractTests` は、登録処理とSkinWeightタブが形式に求める条件を検査します。
Mayaは要りません。

```python
import unittest
from wipskin import api
from wipskin.api.testing import SkinFormatContractTests
from my_studio_skin.format import StudioSkin


class TestStudioSkinContract(SkinFormatContractTests, unittest.TestCase):
    format_class = StudioSkin

    def make_sample_data(self):      # enables the write/read round trip
        return api.SkinWeightData("body", ["hip", "knee"], [1, 0, 0.5, 0.5])
```

検査するのは、識別情報のフィールド、拡張子、登録（modeと設定キー）、宣言した既定値、可用性、ファイルの一覧です。
`make_sample_data` を書いた場合は、`write_weights` で書いたファイルを `read_weights` で読み、同じウェイトに戻ることも検査します。
バインドや適用のようなシーン側の動作はMayaが必要なため、この検査には含みません。

## 8. プラグインを翻訳する

WipSkinのウィンドウは日本語でも表示できます（Options > Language）。
翻訳はコード中の英語の文言をキーに引くので、翻訳の無い文言は英語のまま表示します。

```python
# my_studio_skin/ui/adapter.py
from wipskin.api import tr

feedback.display_info(tr("Exported {count} file(s)", count=len(paths)))
```

- ユーザーが読む文言（ラベル、ツールチップ、ダイアログのタイトルとメッセージ）は、すべて `tr()` で包みます。
- 値はf-stringで組み立てず、`{name}` のフィールドで渡します。
  翻訳する側で語順を入れ替えられるようにするためです。
  `tr` の第1引数は位置専用なので、フィールド名を `source` にしても衝突しません。
- 識別子（設定キー、ファイルの拡張子、`.jSkin` のような形式の名前）は包みません。
- 翻訳ファイルはコードの隣に置き、入口のモジュールでフォルダを1回だけ登録します。

```
my_studio_skin/
    plugin.py
    locales/
        ja.json          {"Exported {count} file(s)": "{count}個のファイルを書き出しました"}
```

```python
# my_studio_skin/plugin.py
import os
from wipskin import api

api.register_locales(os.path.join(os.path.dirname(__file__), "locales"))
```

- カタログは、英語の文言から翻訳への対応を書いたJSONオブジェクトです。
  翻訳には、原文と同じ `{フィールド}` を残します。
- 言語を読み込むときに、プラグインのカタログをWipSkinのカタログと統合します。
  同じ文言を2つのカタログが訳していれば、あとから登録したほうを使います。
  WipSkinがすでに訳している文言（例: "Set a weight directory first."）は、プラグインのカタログに書かなくて構いません。
- 形式がクラス属性で宣言する文言（`viewer_title`、`viewer_selector_label`、`viewer_selector_tooltip`、`viewer_print_tooltip`、`viewer_meta_tooltip`）は、タブが表示するときに `tr()` を通します。
  そのため、これらの文字列もカタログで訳します。
- クラスやモジュールの定数として組み立てた文字列は、import時に1回だけ評価され、言語を切り替えても変わりません。
  こうした文字列は、表示する箇所で `tr()` を通します。
- プラグインにカタログのファイルが無い言語では、プラグインの文言は英語のままです。
  読めないカタログは警告を出して読み飛ばし、ウィンドウは止まりません。
- 言語を切り替えると、ウィンドウを開き直します。
  文言はすべてウィジェットを作る時点で決まるためです。
- WipSkinが自分のカタログに対して行っている検査（`tr("...")` に渡した文言すべてに訳があり、使われない訳が無いこと）は、プラグインでも実行できます。
  ひな形は `tests/test_i18n_coverage.py` です。

## 9. 形式のリファレンス

`wipskin.api.SkinFormat`（`SkinWeightFormat` の別名）のメンバーは次のとおりです。

| メンバー | 既定値 | 用途 |
|---|---|---|
| `mode`、`label`、`extensions` | 必須 | 識別情報とファイル |
| `viewer_title` | `"<label> Viewer"` | ビューアのグループのタイトル |
| `metadata_format` | `mode` | サイドカーの `"format"`。ファイルごとに変えるときは `get_metadata_format(path)` |
| `export_auto_naming_setting` | 自動で作るキー | Auto Namingのチェックボックスの設定 |
| `pack_extensions` | `()` | Files一覧でパックとして色を付ける拡張子 |
| `is_text_format` | `False` | ファイルに文字列の置換をかけても壊れないか |
| `supports_temp_file`、`get_temp_file_path()` | `False`、`None` | Import TempとExport Tempのボタン |
| `has_chunk_selector` と `viewer_selector_label`、`viewer_selector_tooltip`、`viewer_print_tooltip` | オフ | ビューアの選択行とPrintボタン |
| `viewer_meta_tooltip` | 汎用の文言 | ビューアのメタ情報欄のツールチップ |
| `fallback_rank` | `100` | 保存された形式が使えないときに、タブが代わりに選ぶ順位。値が小さいほど優先 |
| `get_availability()`、`get_unavailable_reason()` | 使える | このセッションで形式を無効にする |
| `get_default_settings()` | `{}` | 形式が読む設定キーの既定値 |
| `describe(path)` | コーデックがあればその要約、無ければ空 | ビューアの内容 |
| `read_weights(path)`、`write_weights(path, data)` | 未実装 | レベル2のコーデック |
| `list_files(directory)`、`get_file_predicate()` | 拡張子で判定 | Files一覧に出すファイル |
| `expand_file_names(directory, names)` | 選択のまま | 選択した項目に対してArchiveとDeleteが扱うファイル |
| `can_rename_influence(name)` | `False` | ビューアでインフルエンス名を変えてよいか |
| `influence_node_types()` | 制限なし | シーンに存在するとみなすインフルエンスのノードタイプ |
