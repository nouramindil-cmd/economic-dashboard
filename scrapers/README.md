# سحب بيانات بوابة أم القرى (uqn.gov.sa)

سكربت (بنسختين: **Python** و **R**) لسحب **اللوائح والأنظمة** و**قرارات مجلس الوزراء** من بوابة أم القرى
وإخراجها في ملف JSON.

## التثبيت

```bash
pip install -r scrapers/requirements.txt
```

## الاستخدام

سحب **كل** اللوائح والأنظمة:

```bash
python scrapers/uqn_scraper.py --section rules --all -o data/uqn_rules.json
```

سحب أول 12 قرارًا من قرارات مجلس الوزراء (٦ قرارات في كل صفحة → صفحتان):

```bash
python scrapers/uqn_scraper.py --section decisions --limit 12 -o data/uqn_decisions.json
```

### الخيارات

| الخيار | الوصف |
|---|---|
| `--section rules\|decisions` | القسم المستهدف (الافتراضي `rules`) |
| `--url URL` | رابط قائمة مخصص يتجاوز `--section` |
| `--all` | المرور على كل الصفحات حتى تنتهي النتائج |
| `--pages N` | عدد صفحات القائمة (الافتراضي 2) |
| `--limit N` | حد أقصى لعدد العناصر (0 = بلا حد) |
| `--engine http\|playwright` | `http` سريع، و`playwright` للصفحات المبنية بجافاسكربت |
| `--delay S` | ثوانٍ بين الطلبات (الافتراضي 1) — احترامًا للخادم |
| `--list-only` | طباعة الروابط فقط للتشخيص |
| `--dump-html DIR` | حفظ HTML الخام للتشخيص |
| `-o, --out` | مسار ملف JSON الناتج |

إذا لم يجد السكربت أي روابط بمحرك `http`، فالصفحة تُبنى بجافاسكربت — أعد
التنفيذ بـ:

```bash
pip install playwright && playwright install chromium
python scrapers/uqn_scraper.py --section rules --all --engine playwright -o data/uqn_rules.json
```

## نسخة R (لمستخدمي RStudio)

الملف `scrapers/uqn_scraper.R` يعطي نفس المخرجات تمامًا.

### ١. تثبيت الحزم (مرة واحدة)

```r
install.packages(c("rvest", "xml2", "httr2", "jsonlite", "stringr"))
```

> إذا فشل تثبيت `httr2` فالسكربت يعمل بـ `httr` تلقائيًا:
> `install.packages("httr")`

### ٢. التشغيل

مهم: استخدم `encoding = "UTF-8"` مع `source` حتى تُقرأ النصوص العربية صحيحة.

```r
setwd("مسار/مجلد/المشروع")
source("scrapers/uqn_scraper.R", encoding = "UTF-8")

# كل اللوائح والأنظمة
scrape_uqn(section = "rules", all_pages = TRUE, out = "data/uqn_rules.json")

# أول 12 قرارًا من قرارات مجلس الوزراء
scrape_uqn(section = "decisions", limit = 12, out = "data/uqn_decisions.json")

# تشخيص: طباعة الروابط فقط
scrape_uqn(section = "rules", list_only = TRUE)

# إذا كانت الصفحة مبنية بجافاسكربت
install.packages("chromote")
scrape_uqn(section = "rules", all_pages = TRUE, engine = "chromote",
           out = "data/uqn_rules.json")
```

### سحب كل شيء: `discover = "ids"`

خريطة الموقع تسرد جزءًا من الأنظمة فقط، والترقيم في الموقع يعمل عبر
AJAX (لاحظ `Disallow: /*page=` و `/ajax/` في robots.txt)، لذا لا يكفيان
لجلب كل العناصر. لكن صفحات التفاصيل تحمل أرقامًا متسلسلة:

```
https://www.uqn.gov.sa/decisions-and-regulations/4001678
```

فوضع `ids` يأخذ الأرقام المعروفة كمرجع، ثم يمر على النطاق الرقمي كاملًا:

```r
scrape_uqn(section = "rules", discover = "ids", out = "uqn_rules.json")
```

الأرقام غير الموجودة (404) تُسجَّل في حقل `skipped` فلا تُفحص مرة أخرى
عند إعادة التشغيل. ولتحديد النطاق يدويًا:

```r
scrape_uqn(section = "rules", discover = "ids",
           id_from = 4000000, id_to = 4002000, out = "uqn_rules.json")
```

### معاملات `scrape_uqn()`

| المعامل | الوصف |
|---|---|
| `section` | `"rules"` اللوائح والأنظمة، `"decisions"` قرارات مجلس الوزراء |
| `url` | رابط قائمة مخصص يتجاوز `section` |
| `all_pages` | `TRUE` للمرور على كل الصفحات |
| `pages` | عدد صفحات القائمة إذا لم تستخدم `all_pages` |
| `limit` | حد أقصى لعدد العناصر (0 = بلا حد) |
| `engine` | `"http"` أو `"chromote"` |
| `discover` | `"auto"` أو `"ids"` (الأشمل) أو `"sitemap"` أو `"pages"` |
| `resume` | `TRUE` لمتابعة ملف موجود بدل إعادة السحب |
| `id_from` / `id_to` / `id_pad` | حدود النطاق الرقمي في وضع `ids` |
| `delay` | ثوانٍ بين الطلبات |
| `list_only` | `TRUE` لطباعة الروابط فقط |
| `out` | مسار ملف JSON الناتج |

الدالة تُرجع البيانات أيضًا داخل R، فتقدر تحوّلها لجدول:

```r
items <- scrape_uqn(section = "rules", all_pages = TRUE)
df <- do.call(rbind, lapply(items, function(x) data.frame(
  number = x$number %||% NA, title = x$title, stringsAsFactors = FALSE)))
```

## صيغة المخرجات

```json
{
  "source_url": "https://www.uqn.gov.sa/decisions/rules-and-regulations",
  "section": "rules",
  "scraped_at": "2026-08-31T10:00:00+0000",
  "count": 2,
  "items": [
    {
      "url": "https://www.uqn.gov.sa/decisions/rules-and-regulations/2002",
      "order": 1,
      "title": "نظام المعاملات المدنية",
      "type": "مرسوم ملكي",
      "number": "م/191",
      "issue_date_hijri": "29/11/1444",
      "publish_date_hijri": "1448-3-15",
      "publish_date_gregorian": "28-08-2026",
      "publish_date_raw": "1448-3-15 الموافق 28-08-2026",
      "subtitle": "مرسوم ملكي رقم (م/191) وتاريخ 29/11/1444هـ",
      "content_paragraphs": ["المادة الأولى: ...", "..."],
      "content_text": "النص الكامل...",
      "content_html": "<article id=\"article-content\">...</article>"
    }
  ]
}
```

## الحقول

- `title` — من `h1.article-title`
- `number` / `type` / `issue_date_hijri` — مستخرجة من `p.article-subtitle`
  (وإن غابت، من العنوان)
- `publish_date_hijri` / `publish_date_gregorian` — من `div.date-item span`
- `content_text` — النص الكامل من `article#article-content` أو `.article-desc`
- `content_html` — الـ HTML الأصلي للمحتوى (يفيد للحفاظ على التنسيق)

## ملاحظات

- تُزال محارف اتجاه النص (RLM/LRM) وتُحوَّل الأرقام العربية-الهندية
  (`٠١٢٣`) إلى أرقام لاتينية في حقول الأرقام والتواريخ.
- روابط القوائم تُجمع بمحدّدات متعددة مع تجاهل روابط التنقل والروابط
  الخارجية، فإن غيّر الموقع تصميمه استخدم `--list-only` و`--dump-html`
  لتعديل المحدّدات في `extract_item_links`.
- التنقّل بين الصفحات يجري عبر `?page=N`، ومع محرك playwright يوجد بديل
  بالضغط على أزرار الترقيم إن لم يعمل المعامل.
