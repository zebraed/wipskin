<p align="center">
  <img src="python/wipskin/ui/icons/wipskin.svg" alt="WipSkin" width="96">
</p>

# WipSkin

[English](README.md) | 日本語

WipSkinは、Mayaのスキンウェイトとデフォーマウェイトを管理し、ファイルへExport / Importするツールです。
スキンウェイトとデフォーマウェイト（cluster、softModなど）をMaya XMLで扱い、バージョン付きのファイル一覧を備えた1つのウィンドウから操作します。

mGearとngSkinToolsにはプラグインとして対応しています。
それぞれがMayaに導入されていれば、そのファイル形式も扱えます。

## 概要

WipSkinのウィンドウは、ウェイトファイルの一覧と、Import / Exportのボタンでできています。

| 機能 | 説明 |
| --- | --- |
| SkinWeight | スキンウェイトをMaya deformerWeights XML（`.xml`）で扱います。スキンをレイヤーに分けるWIPパックも書き出せます。mGearかngSkinToolsが導入されていれば、Formatのリストでその形式も選べます（[オプションの形式](#オプションの形式)を参照）。 |
| DeformerWeight | スキン以外のデフォーマのウェイトをXMLで扱います。 |
| バージョン付きファイル | Exportするたびに `name.0001.ext`、`name.0002.ext` と連番で保存できます。一覧には全バージョンか、最新だけを出せます。 |
| ビューアとコメント | ファイルを選ぶと、中身と使っているインフルエンスを表示します。ファイルの横に保存するコメントも付けられます。 |
| ファイル管理 | ウィンドウの中で、ウェイトファイルのリネーム、アーカイブ、削除、復元ができます。 |

## 動作環境

| 項目 | 備考 |
| --- | --- |
| Maya | 2023、2024、2025、2026、2027 |
| mGear | 任意。mGear 4.x以降が入っていると、mGear形式を使えます。 |
| ngSkinTools | 任意。ngSkinTools2はMaya 2027に同梱されていて、入っているとngSkinTools形式を使えます。それ以前のMayaでは、ngSkinTools2を別途導入する必要があります。 |
| wipskin_native | 任意。XMLの読み書きを速くするモジュールです。ロードできたときに限り自動で使います。Python 3.10以上が必要です。 |

XML形式とDeformerWeightは、ほかに何も導入せずに動きます。
必要なパッケージが無い形式はFormatのリストでグレーアウトされ、足りないものがツールチップに出ます。

## インストール

1. このリポジトリを任意の場所にコピーします（例: `D:/tools/wipskin`）。
2. その中の `python` フォルダを、Mayaの `PYTHONPATH` に追加します（例: `Maya.env`）。

   ```
   PYTHONPATH=D:/tools/wipskin/python
   ```

   今のセッションだけで使うなら、Script Editorで次を実行します。

   ```python
   import sys
   sys.path.insert(0, r"D:/tools/wipskin/python")
   ```

## 使い方

Script EditorのPythonタブから開きます。

```python
import wipskin
wipskin.showUI()
```

ウィンドウはドッキングできます。
もう一度開くと、前のウィンドウを閉じてから開き直します。
ウィンドウサイズ、オプション、最後に使ったフォルダ、選んだFormatは、セッションをまたいで保存します。

### ウィンドウ

| 部分 | 説明 |
| --- | --- |
| Weight Dir | ウェイトファイルを置くフォルダです。setで参照するか、パスを直接入力します。横の履歴アイコンを右クリックすると、最近使ったフォルダを選べます。 |
| Version View | Latestは各ファイルの最新バージョンだけを、Fullは全バージョンを表示します。 |
| Files | フォルダ内のウェイトファイルです。選んでImportを押すと、シーンに適用します。 |
| Viewer | 選んだファイルの中身です。インフルエンスをダブルクリックするとMayaで選択します。select allは、シーンにあるインフルエンスをまとめて選択します。 |
| Comment | 選んだファイルへのメモです。Update Commentを押すと、Exportし直さずに保存します。 |
| Import Options / Export Options | 折りたたみ式のパネルです。中身は選んでいるFormatで変わります。 |

#### Filesリストの右クリックメニュー

| 項目 | 説明 |
| --- | --- |
| Export All Skins in Scene... | SkinWeightタブだけにあります。シーン内のスキン付きメッシュを、メッシュごとに1ファイルずつ、メッシュ名で書き出します。今のFormatと、そのExportオプションを使います。書き出す前に、対象メッシュの一覧で確認を求めます。 |
| Rename | ファイルを1つリネームします。コメントも一緒に移します。 |
| Generate Opposite Side... | XML形式とDeformerWeightタブだけにあります。選んだファイルを、ファイル名と中身にある左右の文字列（例: `_L` を `_R`）を置き換えてコピーします。 |
| Import | 選んだファイルをImportします。 |
| Archive | 選んだファイルを削除せず、`.backup` フォルダへ移します。 |
| Delete | 選んだファイルを削除します。 |
| Show Archives... | アーカイブフォルダを開き、ファイルを元に戻すか、完全に削除します。 |
| Open Directory / Refresh | フォルダをファイルブラウザで開きます。Refreshはフォルダを読み直します。 |

XMLとmGearのファイルでは、インフルエンスリストの右クリックにRename Influence... があります。
シーンでジョイントの名前を変えたあとに、ファイルに保存されたインフルエンス名を合わせるための項目です。

### SkinWeight

1. Mayaでメッシュを選択します。
   ImportとExportは、選択したメッシュの階層を対象にします。
2. Exportを押して名前を決めると、Weight Dirに書き出します。
   Importするときは、リストでファイルを選んでImportを押します。

import asのsaved shapeは、ファイルを書き出し元のメッシュへ適用します。
selected shapeは、名前に関係なく、選択しているメッシュへ適用します。

全Formatに共通のExportオプションは次の2つです。

| オプション | 説明 |
| --- | --- |
| auto naming | 選択したメッシュの名前をファイル名にします。複数のメッシュを選んだときはシーン名を使います。 |
| version number | `name.0001.ext` のように4桁のバージョンを付けます。 |

#### XML

MayaのdeformerWeights XMLです。

| Importオプション | 説明 |
| --- | --- |
| method | メッシュの頂点が1対1で一致しないときの対応づけ方です。`index`、`nearest`、`bilinear`、`barycentric`、`over` から選びます。 |
| mode | replaceはウェイトを上書きし、addは今のウェイトに加算します。 |
| Ignore names | インフルエンスを、名前ではなく並び順で対応づけます。 |
| Normalize weights | ImportのあとにskinClusterを正規化します。 |
| Restore BindPreMatrix | ファイルに保存したバインドポーズを復元します。 |

| Exportオプション | 説明 |
| --- | --- |
| optimize | 小さいウェイトを削り、使われていないインフルエンスを外します。 |
| Save BindPreMatrix | 各インフルエンスのバインドポーズを保存します。Import時にRestore BindPreMatrixで使います。 |
| Export as WIP Skin | 単一のファイルの代わりにWIPパックを書き出します。ダイアログでインフルエンスを名前付きのグループへドラッグして割り当てます。パックはBaseと、グループごとのLayerからなり、スキニング作業をファイル単位に分けられます。 |

#### オプションの形式

ここで説明する形式は、対応するパッケージを導入したときに限りFormatのリストで選べます。
XMLだけで作業するなら、この節は読まなくて構いません。

##### mGear

mGear 4.xが必要です。
`.jSkin` と `.gSkin` のファイル、それに `.gSkinPack` パック（メンバーファイルのリスト）を扱います。
パックを選んでImportすると、中のメンバーをすべて読み込みます。

| Importオプション | 説明 |
| --- | --- |
| Import .gSkinPack Version | パックのメンバーファイルを、どのバージョンで読み込むかを選びます。Latestは、Weight Dir内にある各メンバーファイルの最新バージョンを使います。Recordedは、パックに記録されたファイル名をそのまま使います。ビューアに表示するメンバーも、この選択に従います。 |

| Exportオプション | 説明 |
| --- | --- |
| format | メンバーを `.jSkin`（JSON）か `.gSkin` で書き出します。 |
| Export as .gSkinPack | 選択したすべてのメッシュを、1つのパック（`.gSkinPack`）として書き出します。メンバーのファイル形式は、上のformatで決まります。 |

パックをダブルクリックするか、右クリックメニューから、パックエディタを開けます。
パックエディタでは、メンバーごとに「記録済みのファイルのまま」「最新バージョンを指す」「シーンからExportし直す」のどれかを選び、パックを新しいバージョンとして保存します。

##### ngSkinTools

ngSkinTools形式（`.json`）は、ngSkinTools2のレイヤーを扱います。
ウェイトそのものではなく、skinClusterの上に載せたレイヤーをExport / Importします。
ImportするメッシュにはskinClusterが必要なので、先にXMLやmGearなどでバインドしておきます。

ExportはFilesリストの「Export All Skins in Scene...」も含め、ngSkinToolsのレイヤーが有効なメッシュだけが対象です。
ファイル名は、トランスフォーム名の後ろに `_ngSkintools` が付きます（例: `body_ngSkintools.0001.json`）。
ビューアには、レイヤー数、頂点数、レイヤー名の一覧、使っているインフルエンスを表示します。

| Importオプション | 説明 |
| --- | --- |
| Vertex Transfer | ファイルの頂点を、読み込み先のメッシュへ対応づける方法です。Vertex IDは頂点インデックスで対応づけます（2つのメッシュが同一のとき向け）。Closest Surface Pointは、書き出したメッシュ上の最も近い点へ対応づけます。UV Spaceは、UV空間で同じように対応づけます。 |
| Add Missing Influences | 読み込み前に、skinClusterに無いファイル内のインフルエンスを、ウェイト0で追加します。シーンに存在しないインフルエンスは無視します。初期値はオンです。 |
| Replace Existing Layers | 読み込み前に、skinClusterが既に持つレイヤーを削除します。Choose Layers on Importがオンのときは、選んだレイヤーと同じ名前の既存レイヤーだけを置き換えます。オフのときは、既存のレイヤーの上に追加します。初期値はオンです。 |
| Choose Layers on Import | ファイルごとに、読み込むレイヤーを選ぶダイアログを開きます。キャンセルすると、残りのファイルは読み込みません。初期値はオンです。 |

Exportオプションは、全Formatに共通の2つだけです。

### DeformerWeight

cluster、softModなどのデフォーマのウェイトを、XMLでExport / Importします。

1. デフォームされているジオメトリを選択し、Update deformer listを押します。
2. 左のリストでデフォーマを選びます。
   特定のシェイプだけを書き出すときは、Deformed shapesでシェイプを選びます。
3. Exportを押すと、シェイプごとに `shape_deformer.xml` という名前のファイルを書き出します。
4. ウェイトを戻すときは、ファイルを選んでImportを押します。

Importオプションのimport as、method、Ignore namesは、XML形式と同じ意味です。
Exportオプションはauto namingとversion numberです。

### Options

| メニュー | 説明 |
| --- | --- |
| Options > Language | ウィンドウの表示言語を、英語と日本語で切り替えます。切り替えるとウィンドウを開き直します。 |
| Help > About... | バージョンと作者を表示します。 |

ImportとExportの各オプションは、右クリックのReset To Defaultで初期値に戻せます。

### スクリプト

操作はウィンドウで行う前提です。
Pythonから使う関数は次の2つです。

```python
import wipskin

wipskin.showUI()    # ウィンドウを開く
wipskin.Reload()    # 開発用: パッケージを再読み込みしてから、もう一度 showUI() を呼ぶ
```

## 開発

```bash
python -m pytest tests -q
```

Mayaが必要なテストは、Mayaの外ではスキップします。
`Reload()` が読み直すのは、`wipskin` パッケージと、形式を登録したプラグインです。
`python/wipskin/_native/wipskin_native.pyd` を差し替えたときは、拡張モジュールは読み直せないのでMayaを再起動します。
高速化モジュールを使わず純粋なPythonで動かすには、`WIPSKIN_NO_NATIVE=1` を設定します。

## 形式の追加

スキンウェイトの形式は、WipSkin本体を編集せずにプラグインとして追加できます。
いちばん小さいプラグインは、形式の名前とファイルの拡張子を書くだけです。
それだけで、ファイルの一覧、バージョン付きの名前、リネーム、ビューアの表示が動きます。
読み込みと書き出しの関数を足すと、ImportとExportも使えるようになります。

```python
from wipskin import api


class StudioSkin(api.SkinFormat):
    mode = "studioskin"
    label = "Studio Skin"
    extensions = ("sskin",)


api.register_skin_format(StudioSkin)
```

モジュールを `PYTHONPATH` に置き、`wipskin.showUI()` を呼ぶ前に `WIPSKIN_PLUGINS=my_module` を設定します。
複数のモジュールは、`PATH` と同じ区切り文字で並べます。
書き方は [docs/PLUGINS_JA.md](docs/PLUGINS_JA.md) に、動くサンプルは [examples/plugins](examples/plugins/wipskin_jsonskin) にあります。
同梱のmGearとngSkinToolsも、同じ仕組みのプラグインです（`python/wipskin/plugins`）。

## ライセンス

[MIT License](LICENSE)
