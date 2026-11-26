# プラグインテンプレート

[English](TEMPLATE.md) | 日本語

このフォルダをコピーすると、新しいスキンウェイト形式を作り始められます。
WipSkinはこのフォルダを読み込みません。

## テンプレートからプラグインを作る

1. `_template` を `python/wipskin/plugins/<name>`（同梱プラグインにする場合）か、`PYTHONPATH` 上の `<package>`（外部プラグインにする場合）へコピーします。
2. `plugin.py` と `format.py` にある `wipskin.plugins._template` を、新しいパッケージのパスに置き換えます。
3. `constants.py` で `MODE`、`LABEL`、`EXTENSION` を決めます。
4. `format.py` の `read_weights` / `write_weights` の中身を、自分のファイル形式の処理に置き換えます。
   ファイル一覧、バージョン付きの名前、コメント、ビューアの要約、Import / Exportのシーン側の処理はWipSkinが行います。
5. 読み込ませます。
   - 同梱する場合: `plugins/__init__.py` の `BUNDLED_PLUGINS` に `"wipskin.plugins.<name>.plugin"` を追加します。
   - 外部の場合: `wipskin.showUI()` の前に `WIPSKIN_PLUGINS=<package>.plugin` を設定します。

## ファイル

| ファイル | 役割 |
| --- | --- |
| `constants.py` | 形式のID、表示名、拡張子。importはありません。 |
| `format.py` | 形式のクラスと、読み書きの処理。MayaとQtをimportしません。 |
| `plugin.py` | 入口のモジュール。importすると形式とロケールを登録します。 |
| `locales/ja.json` | `tr()` の文言の日本語訳（英語の原文がキー）。 |

独自のImport / Exportオプションやダイアログが必要なときは、`ui/` パッケージを足して `SkinFormatIO` と `SkinFormatOptions` を書き、`plugin.py` ではそのクラスを登録します（`docs/PLUGINS_JA.md` のレベル2と3を参照）。
Qtのコードは `ui/` の下にだけ置きます。
