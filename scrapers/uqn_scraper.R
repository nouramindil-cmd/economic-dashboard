# -*- coding: utf-8 -*-
# سحب البيانات من بوابة أم القرى (uqn.gov.sa) باستخدام R
#
# الاستخدام في RStudio:
#   source("scrapers/uqn_scraper.R")
#   scrape_uqn(section = "rules", all_pages = TRUE, out = "data/uqn_rules.json")
#   scrape_uqn(section = "decisions", limit = 12, out = "data/uqn_decisions.json")
#
# للتشخيص (طباعة الروابط فقط دون سحب التفاصيل):
#   scrape_uqn(section = "rules", list_only = TRUE)

# ------------------------------------------------------------ المتطلبات

.uqn_require <- function(pkgs) {
  missing <- pkgs[!vapply(pkgs, requireNamespace, logical(1), quietly = TRUE)]
  if (length(missing)) {
    stop("ينقصك تثبيت الحزم التالية:\n  install.packages(c(",
         paste(sprintf('"%s"', missing), collapse = ", "), "))",
         call. = FALSE)
  }
}

.uqn_require(c("rvest", "xml2", "jsonlite", "stringr"))

# للطلبات نستخدم httr2 إن وُجد، وإلا httr الأقدم
.UQN_HTTP <- if (requireNamespace("httr2", quietly = TRUE)) {
  "httr2"
} else if (requireNamespace("httr", quietly = TRUE)) {
  "httr"
} else {
  stop('ينقصك تثبيت حزمة الطلبات:\n  install.packages("httr2")', call. = FALSE)
}

`%||%` <- function(a, b) if (is.null(a) || length(a) == 0) b else a

BASE <- "https://www.uqn.gov.sa"

SECTIONS <- list(
  rules     = "/decisions/rules-and-regulations",       # اللوائح والأنظمة
  decisions = "/decisions/council-of-ministers-decisions" # قرارات مجلس الوزراء
)

UA <- paste(
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# محارف التحكم في اتجاه النص التي تظهر داخل التواريخ في الموقع
BIDI <- c("\u200b", "\u200c", "\u200d", "\u200e", "\u200f", "\u202a",
          "\u202b", "\u202c", "\u202d", "\u202e", "\u2066", "\u2067",
          "\u2068", "\u2069", "\ufeff")

# الأرقام العربية-الهندية ٠-٩
ARABIC_DIGITS <- c("\u0660", "\u0661", "\u0662", "\u0663", "\u0664",
                   "\u0665", "\u0666", "\u0667", "\u0668", "\u0669")

NAV_HINTS <- c("/login", "/register", "/search", "/contact", "/about",
               "/privacy", "/terms", "/sitemap", "/rss", "/help", "/faq",
               "/news", "javascript:", "mailto:", "tel:", "#")

# ------------------------------------------------------- أدوات مساعدة

# إزالة محارف الاتجاه وتوحيد المسافات
clean_text <- function(x) {
  if (is.null(x) || length(x) == 0) return("")
  x <- x[1]
  if (is.na(x)) return("")
  for (ch in BIDI) x <- gsub(ch, "", x, fixed = TRUE)
  x <- gsub(" ", " ", x, fixed = TRUE)
  x <- gsub("[ \t]+", " ", x)
  x <- gsub("\n{3,}", "\n\n", x)
  trimws(x)
}

# تحويل الأرقام العربية-الهندية (٠١٢٣) إلى أرقام لاتينية
to_ascii_digits <- function(x) {
  if (is.null(x) || length(x) == 0) return(NA_character_)
  x <- x[1]
  if (is.na(x)) return(NA_character_)
  for (i in seq_along(ARABIC_DIGITS)) {
    x <- gsub(ARABIC_DIGITS[i], as.character(i - 1L), x, fixed = TRUE)
  }
  x
}

# إضافة/تحديث أي معامل في الرابط
add_param <- function(url, param, value) {
  pattern <- paste0("([?&]", param, "=)[^&]*")
  if (grepl(pattern, url)) {
    sub(pattern, paste0("\\1", value), url)
  } else if (grepl("\\?", url)) {
    paste0(url, "&", param, "=", value)
  } else {
    paste0(url, "?", param, "=", value)
  }
}

with_page <- function(url, page) add_param(url, "page", page)

# ------------------------------------------------------------- الجلب

# جلب صفحة مع إعادة المحاولة بتأخير متضاعف.
# أخطاء 4xx (مثل 404) تفشل فورًا دون إعادة محاولة - مهم عند مسح
# نطاق أرقام فيه فجوات، وإلا استغرق كل رقم مفقود عدة ثوانٍ.
fetch_html <- function(url, tries = 4, timeout = 30) {
  delay <- 2
  last_err <- NULL
  for (i in seq_len(tries)) {
    result <- tryCatch({
      if (.UQN_HTTP == "httr2") {
        req <- httr2::request(url)
        req <- httr2::req_user_agent(req, UA)
        req <- httr2::req_headers(req, `Accept-Language` = "ar,en;q=0.8")
        req <- httr2::req_timeout(req, timeout)
        req <- httr2::req_error(req, is_error = function(resp) FALSE)
        resp <- httr2::req_perform(req)
        list(status = httr2::resp_status(resp),
             body = httr2::resp_body_string(resp))
      } else {
        resp <- httr::GET(
          url,
          httr::user_agent(UA),
          httr::add_headers(`Accept-Language` = "ar,en;q=0.8"),
          httr::timeout(timeout)
        )
        list(status = httr::status_code(resp),
             body = httr::content(resp, as = "text", encoding = "UTF-8"))
      }
    }, error = function(e) {
      last_err <<- conditionMessage(e)
      NULL
    })

    if (!is.null(result)) {
      if (result$status < 400) return(result$body)
      if (result$status < 500) {
        stop(structure(
          class = c("uqn_missing", "error", "condition"),
          list(message = sprintf("HTTP %d", result$status), call = NULL)
        ))
      }
      last_err <- sprintf("HTTP %d", result$status)
    }
    if (i < tries) Sys.sleep(delay)
    delay <- delay * 2
  }
  stop("تعذّر جلب ", url, " : ", last_err, call. = FALSE)
}

# بديل يستخدم متصفحًا حقيقيًا - لازم إذا كانت الصفحة تُبنى بجافاسكربت
fetch_html_chromote <- function(url, wait = 3) {
  .uqn_require("chromote")
  session <- chromote::ChromoteSession$new()
  on.exit(try(session$close(), silent = TRUE), add = TRUE)
  session$Page$navigate(url)
  try(session$Page$loadEventFired(wait_ = TRUE), silent = TRUE)
  Sys.sleep(wait)
  session$Runtime$evaluate("document.documentElement.outerHTML")$result$value
}

# ------------------------------------------------------------ التحليل

# أول نص غير فارغ من قائمة محدّدات CSS
first_text <- function(doc, selectors) {
  for (sel in selectors) {
    els <- rvest::html_elements(doc, sel)
    if (length(els) > 0) {
      value <- clean_text(rvest::html_text2(els[[1]]))
      if (nzchar(value)) return(value)
    }
  }
  NA_character_
}

# هل المسار يخص نظامًا/لائحة/قرارًا؟ (وليس خبرًا أو صفحة تنقل)
# ملاحظة: صفحات التفاصيل في الموقع تحت /decisions-and-regulations/<رقم>
# وهو مسار مختلف عن مسار القائمة /decisions/rules-and-regulations
is_item_path <- function(path, list_path) {
  if (grepl("/news", path, fixed = TRUE)) return(FALSE)
  has_id <- grepl("/[0-9]{3,}$", path)
  if (!has_id) return(FALSE)
  if (grepl("(decision|regulation|rule)", path, ignore.case = TRUE)) return(TRUE)
  startsWith(path, paste0(list_path, "/"))
}

# استخراج روابط صفحات التفاصيل من صفحة القائمة، مع الحفاظ على الترتيب
extract_item_links <- function(html_txt, list_url) {
  doc <- rvest::read_html(html_txt)
  parts <- xml2::url_parse(list_url)
  list_path <- sub("/$", "", parts$path)
  host <- parts$server

  anchors <- rvest::html_elements(doc, "a[href]")
  hrefs <- rvest::html_attr(anchors, "href")

  links <- character(0)
  for (href in hrefs) {
    if (is.na(href) || !nzchar(trimws(href))) next
    lower <- tolower(href)
    if (any(vapply(NAV_HINTS, function(p) grepl(p, lower, fixed = TRUE),
                   logical(1)))) next
    abs_url <- xml2::url_absolute(href, list_url)
    p <- xml2::url_parse(abs_url)
    if (nzchar(p$server) && p$server != host) next
    path <- sub("/$", "", p$path)
    if (!nzchar(path) || path == list_path) next
    if (!is_item_path(path, list_path)) next
    key <- sub("#.*$", "", abs_url)
    if (!(key %in% links)) links <- c(links, key)
  }
  links
}

# كل الصيغ المحتملة لرابط الصفحة رقم n: معاملات استعلام ومسارات
page_url_builders <- function(list_url) {
  base_path <- sub("/$", "", list_url)
  params <- c("page", "pageNumber", "pageIndex", "PageNumber", "Page",
              "pageNo", "pageNum", "p", "pg", "start", "offset")

  builders <- lapply(params, function(prm) {
    force(prm)
    function(n) add_param(list_url, prm, n)
  })
  names(builders) <- paste0("?", params, "=n")

  # صيغ المسارات - وهي شائعة ولم تكن مُجرّبة سابقًا
  builders[["/page/n"]] <- function(n) paste0(base_path, "/page/", n)
  builders[["/n"]]      <- function(n) paste0(base_path, "/", n)
  builders[["/p/n"]]    <- function(n) paste0(base_path, "/p/", n)
  builders
}

# اكتشاف آلية الترقيم: نجرّب كل صيغة على الصفحة 2 ونأخذ أول واحدة
# تعطي عناصر جديدة فعلًا. تُرجع دالة تبني رابط أي صفحة.
detect_pagination <- function(getter, list_url, first_links, delay = 1) {
  builders <- page_url_builders(list_url)
  for (nm in names(builders)) {
    build <- builders[[nm]]
    probe <- tryCatch(getter(build(2)), error = function(e) NULL)
    if (is.null(probe)) next
    found <- extract_item_links(probe, list_url)
    if (length(found) > 0 && length(setdiff(found, first_links)) > 0) {
      message(sprintf("آلية الترقيم المكتشفة: %s", nm))
      return(build)
    }
    Sys.sleep(delay)
  }
  NULL
}

# ------------------------------------------------ قائمة القسم نفسها

# محاولة إرجاع القائمة كاملة في طلب واحد عبر معامل حجم الصفحة.
# أرخص بكثير من المرور على 144 صفحة إن دعمه الخادم.
detect_page_size <- function(getter, list_url, first_links, delay = 0.5) {
  params <- c("pageSize", "PageSize", "page_size", "size", "limit", "take",
              "count", "rows", "perPage", "per_page", "pageLength")
  for (prm in params) {
    for (val in c(1000L, 500L)) {
      probe <- tryCatch(getter(add_param(list_url, prm, val)),
                        error = function(e) NULL)
      if (is.null(probe)) next
      found <- extract_item_links(probe, list_url)
      if (length(found) > length(first_links)) {
        message(sprintf("معامل حجم الصفحة: %s=%d اعاد %d رابط",
                        prm, val, length(found)))
        return(found)
      }
      Sys.sleep(delay)
    }
  }
  NULL
}

# المرور على صفحات القائمة بمتصفح حقيقي.
# يعمل مهما كانت آلية الترقيم (AJAX أو غيره) لأنه يضغط الأزرار فعليًا.
#
# ملاحظتان تعلّمناهما من الموقع:
#  - البحث عن أي عنصر نصه "2" يلتقط أرقامًا غير أزرار الترقيم، لذا
#    نبدأ بحاويات الترقيم ثم نتوسّع.
#  - المحتوى يُحمَّل عبر AJAX بعد الضغط، فلا يصح انتظار مدة ثابتة؛
#    ننتظر حتى تتغيّر الروابط فعلًا.
collect_links_browser <- function(list_url, max_pages = 200,
                                  timeout = 15, step = 0.5) {
  .uqn_require("chromote")
  b <- chromote::ChromoteSession$new()
  on.exit(try(b$close(), silent = TRUE), add = TRUE)

  html_now <- function() {
    b$Runtime$evaluate("document.documentElement.outerHTML")$result$value
  }
  eval_js <- function(js) {
    tryCatch(b$Runtime$evaluate(js)$result$value, error = function(e) NULL)
  }

  b$Page$navigate(list_url)
  Sys.sleep(6)
  links <- extract_item_links(html_now(), list_url)
  message(sprintf("صفحة 1: %d رابط", length(links)))
  if (length(links) == 0) {
    stop("لم تظهر أي عناصر في الصفحة الأولى.", call. = FALSE)
  }

  # يضغط رقم الصفحة داخل حاوية ترقيم، وإلا زر "التالي"،
  # ويُرجع وصف ما ضغطه للتشخيص
  click_js <- '(function(n){
    var vis = function(e){ return e.offsetParent !== null; };
    var leaf = function(e){ return e.children.length === 0; };
    var desc = function(e,how){ return how + "|" + e.tagName + "|" +
      String(e.className||"").slice(0,40); };

    var boxes = Array.prototype.slice.call(document.querySelectorAll(
      "[class*=pag],[class*=Pag],[class*=pager],nav,ul"));

    // 1) رقم الصفحة داخل حاوية ترقيم
    for (var i = 0; i < boxes.length; i++) {
      var kids = Array.prototype.slice.call(
        boxes[i].querySelectorAll("a,button,li,span"));
      for (var j = 0; j < kids.length; j++) {
        var e = kids[j];
        if (leaf(e) && vis(e) && e.textContent.trim() === String(n)) {
          e.scrollIntoView({block:"center"}); e.click();
          return desc(e,"num-in-pager");
        }
      }
    }
    // 2) زر التالي
    var all = Array.prototype.slice.call(
      document.querySelectorAll("a,button,li,span"));
    for (var k = 0; k < all.length; k++) {
      var x = all[k];
      var sig = (x.getAttribute("aria-label")||"") + " " +
                String(x.className||"") + " " + x.textContent.trim();
      if (vis(x) && /next|التالي|\u00bb|\u203a/i.test(sig) &&
          !/prev|السابق/i.test(sig)) {
        x.scrollIntoView({block:"center"}); x.click();
        return desc(x,"next");
      }
    }
    // 3) أي عنصر ورقي نصه رقم الصفحة
    for (var m = 0; m < all.length; m++) {
      var y = all[m];
      if (leaf(y) && vis(y) && y.textContent.trim() === String(n)) {
        y.scrollIntoView({block:"center"}); y.click();
        return desc(y,"num-anywhere");
      }
    }
    return "none";
  })(%d)'

  page <- 2
  while (page <= max_pages) {
    before <- links
    what <- eval_js(sprintf(click_js, page))
    if (is.null(what) || identical(what, "none")) {
      message(sprintf("صفحة %d: لا يوجد زر للانتقال - انتهت القائمة.", page))
      break
    }

    # ننتظر حتى تظهر روابط جديدة، لا مدة ثابتة
    waited <- 0
    found <- before
    repeat {
      Sys.sleep(step); waited <- waited + step
      found <- extract_item_links(html_now(), list_url)
      if (length(setdiff(found, before)) > 0) break
      if (waited >= timeout) break
    }

    fresh <- setdiff(found, before)
    if (length(fresh) == 0) {
      message(sprintf("صفحة %d: ضُغط [%s] لكن لم يتغيّر المحتوى خلال %g ثانية.",
                      page, what, timeout))
      break
    }
    links <- c(links, fresh)
    message(sprintf("صفحة %d: %d جديد | المجموع %d  [%s]",
                    page, length(fresh), length(links), what))
    page <- page + 1
  }
  links
}

# أداة تشخيص: تعرض عناصر الترقيم الحقيقية في الصفحة
inspect_pager <- function(list_url = paste0(BASE, SECTIONS$rules)) {
  .uqn_require("chromote")
  b <- chromote::ChromoteSession$new()
  on.exit(try(b$close(), silent = TRUE), add = TRUE)
  b$Page$navigate(list_url)
  Sys.sleep(7)
  js <- '(function(){
    var out=[], seen={};
    var all=Array.prototype.slice.call(
      document.querySelectorAll("a,button,li,span,div"));
    all.forEach(function(e){
      var t=e.textContent.trim();
      if(/^[0-9]{1,3}$/.test(t) && e.children.length===0 && e.offsetParent!==null){
        var k=e.tagName+String(e.className||"");
        if(seen[k]) return; seen[k]=1;
        out.push(t+" | "+e.tagName+" | class="+String(e.className||"-")+
                 " | href="+(e.getAttribute("href")||"-")+
                 " | onclick="+(e.getAttribute("onclick")||"-")+
                 " | parent="+String(e.parentElement?e.parentElement.className:"-").slice(0,40));
      }
    });
    return out.slice(0,20).join("\n");
  })()'
  cat(b$Runtime$evaluate(js)$result$value, "\n")
  invisible(NULL)
}

# ---------------------------------------------------- خريطة الموقع

# قراءة روابط من ملف sitemap (مع النزول داخل فهارس الخرائط)
collect_sitemap_urls <- function(sitemap_url, depth = 0, max_depth = 3) {
  txt <- tryCatch(fetch_html(sitemap_url, tries = 2), error = function(e) NULL)
  if (is.null(txt)) return(character(0))
  doc <- tryCatch(xml2::read_xml(txt), error = function(e) NULL)
  if (is.null(doc)) return(character(0))

  locs <- xml2::xml_text(xml2::xml_find_all(doc, "//*[local-name()='loc']"))
  locs <- trimws(locs)
  if (length(locs) == 0) return(character(0))

  # إذا كان الملف فهرس خرائط، ننزل داخل كل خريطة
  if (identical(xml2::xml_name(xml2::xml_root(doc)), "sitemapindex") &&
      depth < max_depth) {
    out <- character(0)
    for (u in locs) {
      out <- c(out, collect_sitemap_urls(u, depth + 1, max_depth))
    }
    return(unique(out))
  }
  unique(locs)
}

# البحث عن كل روابط الأنظمة/القرارات عبر خريطة الموقع
links_from_sitemap <- function(list_url) {
  parts <- xml2::url_parse(list_url)
  origin <- paste0(parts$scheme, "://", parts$server)

  candidates <- paste0(origin, c("/sitemap.xml", "/sitemap_index.xml",
                                 "/sitemap-index.xml", "/sitemap/sitemap.xml"))

  # robots.txt غالبًا يشير إلى مكان الخريطة
  robots <- tryCatch(fetch_html(paste0(origin, "/robots.txt"), tries = 2),
                     error = function(e) "")
  if (nzchar(robots)) {
    found <- stringr::str_match_all(robots, "(?i)sitemap:\\s*(\\S+)")[[1]]
    if (nrow(found) > 0) candidates <- unique(c(found[, 2], candidates))
  }

  all_urls <- character(0)
  for (cand in candidates) {
    urls <- collect_sitemap_urls(cand)
    if (length(urls) > 0) {
      message(sprintf("خريطة الموقع %s: %d رابط", cand, length(urls)))
      all_urls <- unique(c(all_urls, urls))
    }
  }
  if (length(all_urls) == 0) return(character(0))

  keep <- vapply(all_urls, function(u) {
    path <- sub("/$", "", xml2::url_parse(u)$path)
    is_item_path(path, sub("/$", "", xml2::url_parse(list_url)$path))
  }, logical(1))

  unname(all_urls[keep])
}

# ------------------------------------------- الصيغة القديمة details

# الموقع يحتفظ بأرشيفه القديم بروابط الشكل /details?p=12918 وهي الغالبية
# العظمى من خريطة الموقع. اللوائح والأنظمة القديمة موجودة هناك، ولا تظهر
# تحت /decisions-and-regulations إلا الحديثة منها.
links_from_details <- function(list_url) {
  parts <- xml2::url_parse(list_url)
  origin <- paste0(parts$scheme, "://", parts$server)

  candidates <- paste0(origin, c("/sitemap_0.xml", "/sitemap.xml"))
  robots <- tryCatch(fetch_html(paste0(origin, "/robots.txt"), tries = 2),
                     error = function(e) "")
  if (nzchar(robots)) {
    found <- stringr::str_match_all(robots, "(?i)sitemap:\\s*(\\S+)")[[1]]
    if (nrow(found) > 0) candidates <- unique(c(found[, 2], candidates))
  }

  urls <- character(0)
  for (cand in candidates) {
    urls <- unique(c(urls, collect_sitemap_urls(cand)))
  }
  out <- grep("details", urls, value = TRUE)
  message(sprintf("روابط الأرشيف القديم (details): %d", length(out)))
  out
}

# صيغ لا تَرِد إلا في نص نظامي رسمي (وزن عالٍ)
REG_STRONG <- c(
  "يقرر ما يلي", "إن مجلس الوزراء", "رسمنا بما هو آت", "يرسم بما هو آت",
  "بعون الله تعالى", "أمرنا بما هو آت", "وعلى ما قرره مجلس الوزراء"
)

# قرائن مساندة: قوية مجتمعةً لا منفردة
REG_WEAK <- c(
  "المادة الأولى", "المادة الثانية", "المادة الثالثة",
  "بعد الاطلاع على المعاملة", "بعد الاطلاع على الأمر",
  "بعد الاطلاع على المذكرة", "هيئة الخبراء", "اللجنة العامة لمجلس الوزراء",
  "يُعمل بهذا النظام", "أحكام هذا النظام", "ويلغي كل ما يتعارض معه"
)

# عناوين ليست لوائح: فهارس الأعداد، وصيغ الأخبار (فعل في أول العنوان)
NOT_REG_TITLES <- c(
  "^(طرح|أعلن|أعلنت|استقبل|هنأ|هنّأ|وقّع|وقع|بحث|التقى|شارك|افتتح|دشن|دشّن|زار|ترأس|رعى|كرم|كرّم|أطلق|تلقى|بعث|نظم|نظّم)\\s",
  "^(يوجه|يهنئ|يستقبل|يبحث|يلتقي|يرعى|يفتتح|يدشن|يترأس|يعلن|يزور|يطلق)\\s",
  "^(ولي العهد|خادم الحرمين|سمو |معالي |الأمير |الملك )"
)

# عبارات تُميّز عنوان الخبر أينما وردت فيه، لا في بدايته فقط.
# تقارير جلسات مجلس الوزراء تنقل نص القرارات داخلها، فتحمل كل
# القرائن النظامية (يقرر ما يلي، إن مجلس الوزراء) رغم أنها أخبار -
# ولا يفصلها عن القرار الحقيقي إلا عنوانها.
NEWS_TITLE_CONTAINS <- c(
  "يعقد جلسته", "يعقد جلسة", "جلسته الأسبوعية", "جلسة مجلس الوزراء",
  "الاتصال المرئي", "برئاسة خادم الحرمين", "برئاسة ولي العهد",
  "يرأس جلسة", "يرأس الجلسة", "خلال جلسة", "في جلسته الأسبوعية",
  "يستعرض", "يستعرضون", "يطّلع على", "يطلع على"
)

# هل السجل المستخرَج لائحة/نظام/قرار فعلًا؟
#
# الصفحات الحديثة (/decisions-and-regulations/) تحمل رقمًا في
# p.article-subtitle، أما صفحات الأرشيف القديم (/details?p=) فلا تحمله،
# فنعتمد على وزن القرائن في النص: قرينة قوية واحدة تكفي، أو قرينتان
# ضعيفتان. عبارة مثل "اللائحة التنفيذية" وحدها لا تكفي لأنها تَرِد في
# أخبار تتحدث عن مشاريع أنظمة.
regulation_score <- function(rec) {
  body <- paste(rec$content_text %||% "", rec$subtitle %||% "")
  if (!nzchar(trimws(body))) return(0L)
  strong <- sum(vapply(REG_STRONG, function(m) grepl(m, body, fixed = TRUE),
                       logical(1)))
  weak <- sum(vapply(REG_WEAK, function(m) grepl(m, body, fixed = TRUE),
                     logical(1)))
  as.integer(2L * strong + weak)
}

is_regulation <- function(rec) {
  if (is.null(rec)) return(FALSE)

  title <- rec$title %||% NA_character_
  news_title <- FALSE
  if (!is.na(title)) {
    for (pat in NOT_REG_TITLES) {
      if (grepl(pat, title)) { news_title <- TRUE; break }
    }
  }
  # فهرس عدد: مرفوض دائمًا
  if (!is.na(title) && grepl("^(العدد|عدد)\\s*[0-9]", title)) return(FALSE)

  # تقرير جلسة أو خبر: مرفوض ما لم يحمل رقمًا صريحًا
  if (!is.na(title)) {
    for (m in NEWS_TITLE_CONTAINS) {
      if (grepl(m, title, fixed = TRUE)) {
        num0 <- rec$number %||% NA_character_
        return(!is.na(num0) && nzchar(num0))
      }
    }
  }

  score <- regulation_score(rec)

  # رقم صريح في العنوان الفرعي = الصيغة الحديثة، دليل قاطع
  num <- rec$number %||% NA_character_
  if (!is.na(num) && nzchar(num)) return(TRUE)

  # عنوان بصيغة خبر يحتاج دليلًا نظاميًا قويًا لتجاوزه
  if (news_title) return(score >= 4L)
  score >= 2L
}

# --------------------------------------------------------------------
# إعادة فلترة ملف JSON مسحوب مسبقًا - بلا إنترنت وفي ثوانٍ.
# تفيد لتنقية المخرجات بعد تحسين الفلتر دون إعادة المسح كاملًا.
refilter_json <- function(path, out = NULL, dry_run = FALSE,
                          category = "لوائح وأنظمة") {
  d <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  items <- d$items %||% list()

  keep <- vapply(items, function(x) {
    cc <- x$category %||% NA_character_
    if (!is.null(category) && !is.na(cc)) return(identical(cc, category))
    is_regulation(x)
  }, logical(1))

  cats <- vapply(items, function(x) x$category %||% NA_character_, character(1))
  if (any(!is.na(cats))) {
    message("التصنيفات الموجودة في الملف:")
    print(table(cats, useNA = "ifany"))
  } else {
    message("لا يوجد حقل تصنيف في هذا الملف (سُحب بنسخة أقدم) - ",
            "الفلترة بقرائن النص فقط.")
  }

  message(sprintf("المجموع %d | لوائح %d | مستبعد %d",
                  length(items), sum(keep), sum(!keep)))
  if (sum(!keep) > 0) {
    message("\nعينة من المستبعد:")
    for (x in head(items[!keep], 10)) {
      message("  - ", substr(x$title %||% x$url, 1, 70))
    }
  }
  if (dry_run) return(invisible(items[!keep]))

  if (is.null(out)) out <- path
  d$items <- items[keep]
  d$count <- sum(keep)

  # روابط المستبعَد تُضاف إلى skipped حتى لا يُعاد جلبها عند الاستئناف
  rej_urls <- vapply(items[!keep], function(x) x$url %||% "", character(1))
  rej_urls <- rej_urls[nzchar(rej_urls)]
  d$skipped <- I(unique(c(unlist(d$skipped %||% character(0)), rej_urls)))
  d$rejected <- I(vapply(items[!keep],
                         function(x) x$title %||% x$url %||% "", character(1)))
  con <- file(out, open = "w", encoding = "UTF-8")
  on.exit(close(con), add = TRUE)
  writeLines(jsonlite::toJSON(d, auto_unbox = TRUE, pretty = TRUE,
                              null = "null", na = "null"), con, useBytes = TRUE)
  message(sprintf("\nحُفظ %d لائحة في %s", sum(keep), out))
  invisible(items[keep])
}

# ------------------------------------------------- المسح بالأرقام

# صفحات التفاصيل تحمل أرقامًا متسلسلة (.../decisions-and-regulations/4001678).
# خريطة الموقع تسرد جزءًا منها فقط، والترقيم يعمل عبر AJAX، لذا فأضمن
# طريقة لجلب كل العناصر هي المرور على النطاق الرقمي كاملًا.
links_from_ids <- function(seeds, from = NULL, to = NULL, pad = 0) {
  if (length(seeds) == 0 && (is.null(from) || is.null(to))) {
    stop("لا توجد أرقام مرجعية لتحديد النطاق.", call. = FALSE)
  }

  prefix <- NA_character_
  ids <- integer(0)
  if (length(seeds) > 0) {
    m <- stringr::str_match(seeds, "^(.*/)([0-9]+)/?$")
    ok <- !is.na(m[, 3])
    prefix <- names(sort(table(m[ok, 2]), decreasing = TRUE))[1]
    ids <- as.integer(m[ok, 3])
  }

  lo <- if (is.null(from)) min(ids) - pad else from
  hi <- if (is.null(to))   max(ids) + pad else to

  message(sprintf("مسح النطاق الرقمي %d ... %d (%d رابط)", lo, hi, hi - lo + 1))
  paste0(prefix, seq.int(lo, hi))
}

# أداة تشخيص: تطبع عناصر الترقيم في الصفحة لمعرفة آلية التنقل
diagnose_uqn <- function(section = "rules", url = NULL) {
  if (is.null(url)) url <- paste0(BASE, SECTIONS[[section]])
  doc <- rvest::read_html(fetch_html(url))

  cat("=== روابط تحتوي على page ===\n")
  hrefs <- rvest::html_attr(rvest::html_elements(doc, "a[href]"), "href")
  print(unique(hrefs[grepl("page|Page|[?&]p=", hrefs)]))

  cat("\n=== عناصر الترقيم ===\n")
  els <- rvest::html_elements(doc, "[class*=pag], [class*=Pag], .pager, nav")
  txt <- as.character(els)
  txt <- txt[nchar(txt) < 1500]
  if (length(txt) == 0) cat("(لا يوجد)\n") else cat(head(txt, 15), sep = "\n\n")

  cat("\n=== أزرار/عناصر فيها أرقام صفحات ===\n")
  btns <- rvest::html_elements(doc, "button, li, span[class]")
  labels <- trimws(rvest::html_text2(btns))
  print(unique(labels[grepl("^[0-9]{1,3}$", labels)]))

  invisible(NULL)
}

# استخراج النوع والرقم وتاريخ الإقرار من نص مثل:
#   "قرار رقم (246) وتاريخ 05/03/1448هـ"
#   "مرسوم ملكي رقم (م/191) وتاريخ ٢٩/١١/١٤٤٤هـ"
parse_number_and_date <- function(txt) {
  out <- list(type = NA_character_, number = NA_character_,
              date_hijri = NA_character_)
  txt <- clean_text(txt)
  if (!nzchar(txt)) return(out)

  kind <- stringr::str_match(
    txt, "^\\s*(قرار|مرسوم ملكي|أمر ملكي|أمر سامي|نظام|لائحة)"
  )[1, 2]
  if (!is.na(kind)) out$type <- trimws(kind)

  # رقم ... ( قد يكون "246" أو "م/191" )
  num <- stringr::str_match(
    txt, "رقم\\s*\\(?\\s*([^)\\s]{1,20}?)\\s*\\)?\\s*(?:و?تاريخ|،|$)"
  )[1, 2]
  if (!is.na(num)) {
    out$number <- gsub("^\\(|\\)$", "", trimws(to_ascii_digits(num)))
  }

  dt <- stringr::str_match(
    txt, "تاريخ\\s*([0-9\\u0660-\\u0669]{1,2}\\s*/\\s*[0-9\\u0660-\\u0669]{1,2}\\s*/\\s*[0-9\\u0660-\\u0669]{4})"
  )[1, 2]
  if (!is.na(dt)) out$date_hijri <- gsub("\\s", "", to_ascii_digits(dt))

  out
}

# تفكيك "1448-3-15 الموافق 28-08-2026" إلى هجري وميلادي
parse_publish_dates <- function(txt) {
  out <- list(hijri = NA_character_, gregorian = NA_character_)
  txt <- to_ascii_digits(clean_text(txt))
  if (is.na(txt) || !nzchar(txt)) return(out)

  h <- stringr::str_match(txt, "([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2})")[1, 2]
  if (!is.na(h)) out$hijri <- gsub("/", "-", h)

  g <- stringr::str_match(
    txt, "الموافق\\s*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{4})"
  )[1, 2]
  if (is.na(g)) {
    g <- stringr::str_match(txt, "([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{4})")[1, 2]
  }
  if (!is.na(g)) out$gregorian <- gsub("/", "-", g)

  out
}

# تصنيفات الموقع كما تظهر في مسار التنقل، ومسارات أقسامها
UQN_CATEGORIES <- c(
  "لوائح وأنظمة", "قرارات وزارية", "قرارات مجلس الوزراء",
  "مراسيم ملكية", "أوامر ملكية", "أوامر سامية",
  "اتفاقيات ومعاهدات", "تعاميم"
)

UQN_SECTION_PATHS <- c(
  "rules-and-regulations"            = "لوائح وأنظمة",
  "ministerial-decisions"            = "قرارات وزارية",
  "council-of-ministers-decisions"   = "قرارات مجلس الوزراء",
  "royal-decrees"                    = "مراسيم ملكية",
  "royal-orders"                     = "أوامر ملكية"
)

# استخراج تصنيف الصفحة من مسار التنقل (breadcrumb) فقط.
#
# تنبيه: لا يصح البحث عن رابط القسم بين روابط الصفحة، لأن القائمة
# الرئيسية في كل صفحات الموقع تحتوي روابط كل الأقسام - فتُصنَّف كل
# صفحة (حتى الأخبار) على أنها "لوائح وأنظمة". ولذلك نقتصر هنا على
# عناصر مسار التنقل نفسها، ونعيد NA إن لم نجدها.
page_category <- function(doc) {
  selectors <- c(
    "[itemtype*='BreadcrumbList']", "ol.breadcrumb", "ul.breadcrumb",
    ".breadcrumb", "[class*='breadcrumb']", "[class*='bread-']",
    "[class*='category']", "[class*='categ']"
  )
  for (sel in selectors) {
    els <- tryCatch(rvest::html_elements(doc, sel), error = function(e) NULL)
    if (is.null(els) || length(els) == 0) next
    txt <- clean_text(paste(rvest::html_text2(els), collapse = " | "))
    if (!nzchar(txt)) next
    for (cat in UQN_CATEGORIES) {
      if (grepl(cat, txt, fixed = TRUE)) {
        return(list(category = cat, source = sel))
      }
    }
  }
  list(category = NA_character_, source = NA_character_)
}

# يطبع مسار التنقل الخام - لمعرفة بنيته عند تعذّر التعرف على التصنيف
dump_breadcrumb <- function(url) {
  doc <- rvest::read_html(fetch_html(url, tries = 1))
  cat("===", url, "\n")
  cat("العنوان:", substr(first_text(doc, c("h1.article-title", "h1")), 1, 45), "\n")
  hit <- FALSE
  for (sel in c("[itemtype*='BreadcrumbList']", ".breadcrumb",
                "[class*='breadcrumb']", "[class*='categ']", "nav", "ol", "ul")) {
    els <- rvest::html_elements(doc, sel)
    for (e in els) {
      t <- clean_text(rvest::html_text2(e))
      if (nzchar(t) && nchar(t) < 120 &&
          grepl("لوائح|قرارات|مراسيم|أوامر|أنظمة", t)) {
        cat("  [", sel, "] ", t, "\n", sep = "")
        cat("    HTML: ", substr(gsub("\\s+", " ", as.character(e)), 1, 220), "\n", sep = "")
        hit <- TRUE
      }
    }
    if (hit) break
  }
  if (!hit) cat("  لم يُعثر على مسار تنقل يحمل اسم قسم.\n")
  invisible(NULL)
}

# معاينة سريعة: تطبع تصنيف عدد من الصفحات للتحقق قبل مسح كامل
preview_categories <- function(urls, n = 10) {
  for (u in head(urls, n)) {
    h <- tryCatch(fetch_html(u, tries = 1), error = function(e) NULL)
    if (is.null(h)) { message("مفقود: ", u); next }
    doc <- rvest::read_html(h)
    cc <- page_category(doc)
    message(sprintf("[%s] %s", cc$category %||% "؟",
                    substr(first_text(doc, c("h1.article-title", "h1")), 1, 55)))
  }
  invisible(NULL)
}

# استخراج حقول عنصر واحد (نظام / لائحة / قرار) من صفحة التفاصيل
parse_detail <- function(html_txt, url) {
  doc <- rvest::read_html(html_txt)

  title <- first_text(doc, c("h1.article-title", ".article-title", "h1"))
  cat_info <- page_category(doc)
  publish_raw <- first_text(doc, c(".date-item span", ".date-item",
                                   ".article-date", "time"))
  pub <- parse_publish_dates(publish_raw)

  subtitle <- first_text(doc, c("p.article-subtitle", ".article-subtitle"))
  info <- parse_number_and_date(subtitle)
  if (is.na(info$number)) {  # بعض الصفحات تضع الرقم في العنوان فقط
    alt <- parse_number_and_date(title)
    if (is.na(info$type))       info$type <- alt$type
    if (is.na(info$number))     info$number <- alt$number
    if (is.na(info$date_hijri)) info$date_hijri <- alt$date_hijri
  }

  body <- NULL
  for (sel in c("article#article-content", ".article-desc", "article",
                ".article-body")) {
    els <- rvest::html_elements(doc, sel)
    if (length(els) > 0) { body <- els[[1]]; break }
  }

  paragraphs <- character(0)
  content_html <- NA_character_
  if (!is.null(body)) {
    content_html <- as.character(body)
    nodes <- rvest::html_elements(body, "p, li, h2, h3, h4, td")
    for (node in nodes) {
      # تجاهل الحاويات المتداخلة حتى لا يتكرر النص
      if (length(rvest::html_elements(node, "p, li, table")) > 0) next
      value <- clean_text(rvest::html_text2(node))
      if (nzchar(value)) paragraphs <- c(paragraphs, value)
    }
    if (length(paragraphs) == 0) {
      lines <- strsplit(rvest::html_text2(body), "\n")[[1]]
      lines <- vapply(lines, clean_text, character(1), USE.NAMES = FALSE)
      paragraphs <- lines[nzchar(lines)]
    }
  }

  # إزالة العنوان الفرعي المكرر من أول المحتوى
  if (length(paragraphs) > 0 && !is.na(subtitle) && paragraphs[1] == subtitle) {
    paragraphs <- paragraphs[-1]
  }

  list(
    url                    = url,
    title                  = title,
    category               = cat_info$category,
    type                   = info$type,
    number                 = info$number,
    issue_date_hijri       = info$date_hijri,
    publish_date_hijri     = pub$hijri,
    publish_date_gregorian = pub$gregorian,
    publish_date_raw       = publish_raw,
    subtitle               = subtitle,
    # I() يمنع jsonlite من تحويل قائمة من عنصر واحد إلى نص مفرد
    content_paragraphs     = I(paragraphs),
    content_text           = paste(paragraphs, collapse = "\n\n"),
    content_html           = content_html
  )
}

# ------------------------------------------------------ الدالة الرئيسة

#' سحب اللوائح والأنظمة أو قرارات مجلس الوزراء من بوابة أم القرى
#'
#' @param section    "rules" اللوائح والأنظمة، أو "decisions" قرارات مجلس الوزراء
#' @param url        رابط قائمة مخصص يتجاوز section
#' @param all_pages  TRUE لسحب كل الصفحات حتى تنتهي النتائج
#' @param pages      عدد صفحات القائمة إذا لم تستخدم all_pages
#' @param limit      حد أقصى لعدد العناصر (0 = بلا حد)
#' @param delay      ثوانٍ بين الطلبات، احترامًا للخادم
#' @param engine     "http" أو "chromote" للصفحات المبنية بجافاسكربت
#' @param list_only  TRUE لطباعة الروابط فقط دون سحب التفاصيل
#' @param out        مسار ملف JSON الناتج
scrape_uqn <- function(section = "rules",
                       url = NULL,
                       all_pages = FALSE,
                       pages = 2,
                       limit = 0,
                       delay = 1,
                       engine = c("http", "chromote"),
                       discover = c("auto", "listing", "browser", "details", "ids", "sitemap", "pages"),
                       resume = TRUE,
                       id_from = NULL,
                       id_to = NULL,
                       id_pad = 50,
                       only_regulations = NULL,
                       category = "لوائح وأنظمة",
                       list_only = FALSE,
                       out = NULL) {

  engine <- match.arg(engine)
  discover <- match.arg(discover)
  # في وضع details نمسح الأرشيف كاملًا، فالفلترة بالمحتوى ضرورية
  # في وضعَي listing و browser تأتي العناصر من قائمة القسم نفسها،
  # فهي بالتعريف "لوائح وأنظمة" ولا تحتاج فلترة بقرائن النص
  if (is.null(only_regulations)) only_regulations <- (discover == "details")
  if (discover %in% c("listing", "browser")) {
    only_regulations <- FALSE
    category <- NULL
  }
  getter <- if (engine == "chromote") fetch_html_chromote else fetch_html

  if (is.null(url)) {
    if (!section %in% names(SECTIONS)) {
      stop('section لازم تكون "rules" أو "decisions"', call. = FALSE)
    }
    url <- paste0(BASE, SECTIONS[[section]])
  }
  if (is.null(out)) out <- sprintf("data/uqn_%s.json", section)

  max_pages <- if (all_pages) 1e6 else max(1, pages)

  links <- character(0)

  # --- (1) خريطة الموقع: سريعة لكنها قد تكون ناقصة
  if (discover %in% c("auto", "sitemap", "ids")) {
    sm <- tryCatch(links_from_sitemap(url), error = function(e) character(0))
    if (length(sm) > 0) {
      message(sprintf("عبر خريطة الموقع: %d عنصر", length(sm)))
      links <- unique(c(links, sm))
    } else if (discover %in% c("sitemap")) {
      stop("خريطة الموقع لا تحتوي على عناصر. جرّب discover = \"pages\"",
           call. = FALSE)
    } else {
      message("خريطة الموقع لم تُفد - نعتمد على التنقل بين الصفحات.")
    }
  }

  # --- (2) التنقل بين صفحات القائمة، وتُدمج نتائجه مع الخريطة
  #     (الخريطة قد تسرد جزءًا فقط، فالدمج يضمن التغطية الكاملة)
  if (discover %in% c("auto", "pages", "ids")) {
    first_links <- extract_item_links(getter(url), url)
    message(sprintf("الصفحة 1: %d رابط", length(first_links)))
    links <- unique(c(links, first_links))

    if (discover != "ids" && (all_pages || max_pages > 1) &&
        length(first_links) > 0) {
      build <- detect_pagination(getter, url, first_links, delay)
      if (is.null(build)) {
        message("تعذّر اكتشاف آلية الترقيم.\n",
                "جرّب engine = \"chromote\" أو شغّل diagnose_uqn().")
      } else {
        # seen_pages منفصل عن links: التوقف يعتمد على تكرار نتائج
        # الترقيم نفسه، لا على ما سبق أن جلبته الخريطة
        seen_pages <- first_links
        page <- 2
        while (page <= max_pages) {
          found <- tryCatch(extract_item_links(getter(build(page)), url),
                            error = function(e) character(0))
          if (length(found) == 0) {
            message(sprintf("الصفحة %d: فارغة - انتهت النتائج.", page))
            break
          }
          fresh <- setdiff(found, seen_pages)
          if (length(fresh) == 0) {
            message(sprintf("الصفحة %d: تكرار - انتهت النتائج.", page))
            break
          }
          seen_pages <- c(seen_pages, fresh)
          links <- unique(c(links, fresh))
          message(sprintf("الصفحة %d: %d رابط (%d جديد) | المجموع %d",
                          page, length(found), length(fresh), length(links)))
          if (limit > 0 && length(links) >= limit) break
          page <- page + 1
          Sys.sleep(delay)
        }
      }
    }
  }

  # --- قائمة القسم مباشرة: تعطي بالضبط ما يعرضه الموقع في القسم
  if (discover == "listing") {
    first_links <- extract_item_links(getter(url), url)
    message(sprintf("الصفحة 1: %d رابط", length(first_links)))
    links <- first_links
    big <- detect_page_size(getter, url, first_links, delay)
    if (!is.null(big)) {
      links <- unique(big)
    } else {
      build <- detect_pagination(getter, url, first_links, delay)
      if (is.null(build)) {
        stop("تعذّر الوصول إلى الصفحات التالية عبر الروابط.\n",
             "استخدم discover = \"browser\" (يحتاج: install.packages(\"chromote\"))",
             call. = FALSE)
      }
      seen <- first_links
      page <- 2
      while (page <= max_pages) {
        found <- extract_item_links(getter(build(page)), url)
        if (length(found) == 0) break
        fresh <- setdiff(found, seen)
        if (length(fresh) == 0) break
        seen <- c(seen, fresh)
        links <- unique(c(links, fresh))
        message(sprintf("الصفحة %d: %d جديد | المجموع %d",
                        page, length(fresh), length(links)))
        page <- page + 1
        Sys.sleep(delay)
      }
    }
  }

  if (discover == "browser") {
    links <- collect_links_browser(url, max_pages = if (all_pages) 200 else max_pages)
  }

  # --- (3) الأرشيف القديم: يغطي اللوائح التي لا تظهر بالصيغة الحديثة
  if (discover == "details") {
    links <- unique(c(links, links_from_details(url)))
  }

  # --- (4) المسح بالأرقام: يغطي ما تفوّته الخريطة و AJAX
  if (discover == "ids") {
    links <- links_from_ids(links, from = id_from, to = id_to,
                            pad = id_pad)
  }

  if (limit > 0 && length(links) > limit) links <- links[seq_len(limit)]

  message(sprintf("إجمالي الروابط: %d", length(links)))

  if (list_only) return(links)

  if (length(links) == 0) {
    stop('لم يُعثر على روابط. جرّب engine = "chromote"', call. = FALSE)
  }

  out_dir <- dirname(out)
  if (nzchar(out_dir) && !dir.exists(out_dir)) {
    dir.create(out_dir, recursive = TRUE)
  }

  save_json <- function(items, skipped = character(0)) {
    payload <- list(
      source_url = url,
      section    = section,
      scraped_at = format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"),
      count      = length(items),
      items      = items,
      skipped    = I(skipped)
    )
    json <- jsonlite::toJSON(payload, auto_unbox = TRUE, pretty = TRUE,
                             null = "null", na = "null")
    con <- file(out, open = "w", encoding = "UTF-8")
    on.exit(close(con), add = TRUE)
    writeLines(json, con, useBytes = TRUE)
  }

  # --- استئناف: تخطّي ما سُحب سابقًا إذا كان الملف موجودًا
  items <- list()
  done <- character(0)
  skipped <- character(0)
  if (resume && file.exists(out)) {
    prev <- tryCatch(jsonlite::fromJSON(out, simplifyVector = FALSE),
                     error = function(e) NULL)
    if (!is.null(prev$items) && length(prev$items) > 0) {
      items <- prev$items
      done <- vapply(items, function(x) x$url %||% "", character(1))
      message(sprintf("استئناف: %d عنصر محفوظ مسبقًا سيُتخطى", length(done)))
    }
    if (!is.null(prev$skipped) && length(prev$skipped) > 0) {
      skipped <- unlist(prev$skipped)
      message(sprintf("و%d رابط غير موجود لن يُعاد فحصه", length(skipped)))
    }
  }

  todo <- setdiff(links, c(done, skipped))
  empty_n <- 0L      # سجلات نجح عنوانها وفشل استخراج نصها
  warned <- FALSE
  if (length(todo) == 0) {
    message("كل العناصر مسحوبة مسبقًا - لا شيء جديد.")
    return(invisible(items))
  }

  # --- سحب صفحات التفاصيل
  for (i in seq_along(todo)) {
    link <- todo[i]

    html_txt <- tryCatch(getter(link), error = function(e) {
      if (inherits(e, "uqn_missing")) NA_character_ else stop(e)
    })

    # رقم غير موجود (404) - نسجّله كمتخطّى حتى لا يُفحص مجددًا
    if (length(html_txt) == 1 && is.na(html_txt)) {
      skipped <- c(skipped, link)
    } else {
      record <- tryCatch({
        rec <- parse_detail(html_txt, link)
        if (is.na(rec$title)) NULL
        # التصنيف من الموقع دليل قاطع: نعتمده متى توفّر
        else if (!is.null(category) && !is.na(rec$category) &&
                 !identical(rec$category, category)) NULL
        # وإن غاب التصنيف نرجع إلى قرائن النص
        else if (only_regulations && is.na(rec$category) &&
                 !is_regulation(rec)) NULL
        else rec
      }, error = function(e) {
        list(url = link, error = conditionMessage(e))
      })

      if (is.null(record)) {
        skipped <- c(skipped, link)            # صفحة بلا عنوان = ليست عنصرًا
      } else {
        record$order <- length(items) + 1
        items[[length(items) + 1]] <- record
        if (!nzchar(record$content_text %||% "")) empty_n <- empty_n + 1L
        message(sprintf("[%d/%d] (%d) %s", i, length(todo), length(items),
                        record$title %||% link))

        # إنذار مبكر: لو كل ما جُمع بلا نص فالمشكلة في بنية الصفحة
        if (!warned && length(items) >= 10 && empty_n == length(items)) {
          warning("أول 10 عناصر بلا نص - بنية الصفحات مختلفة. أوقف ",
                  "التنفيذ وراجع المحدّدات.", call. = FALSE, immediate. = TRUE)
          warned <- TRUE
        }
      }
    }

    if (i %% 25 == 0) {
      save_json(items, skipped)
      message(sprintf("--- التقدّم: %d لائحة، %d مستبعد، %d متبقٍ%s ---",
                      length(items), length(skipped), length(todo) - i,
                      if (empty_n > 0) sprintf("، %d بلا نص", empty_n) else ""))
    }
    Sys.sleep(delay)
  }

  save_json(items, skipped)
  message(sprintf("تم الحفظ في %s (%d عنصر، %d متخطّى)",
                  out, length(items), length(skipped)))
  invisible(items)
}
