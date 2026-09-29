# アオカード会員サポート

クレジットカードの問い合わせを、Jev の判断と、カテゴリ専用の文章に分けて返すデモです。

Jev は文章を書きません。1回の呼び出しで、カテゴリ・緊急度・話し方・変更項目・オペレーター要否・情報不足を並列に返します。分岐のしきい値は `app/routing.py` にあります。文章は、決まったカテゴリの担当だけが作ります。

## 起動

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8787
```

`TYPESAFE_API_KEY` が無いときは、画面確認用のキーワード判断で動きます。確信度は較正されていません。右上の表示が「判断はJev」になれば、TypeSafe の API を使っています。

文章生成 API を別に置く場合は、`.env` の `GENERATION_API_KEY` と `GENERATION_BASE_URL` を設定します。未設定なら、カテゴリごとの定型文を返します。

このデモはカードを停止したり、登録を書き換えたりしません。カード番号はサーバに残す前に伏せます。
