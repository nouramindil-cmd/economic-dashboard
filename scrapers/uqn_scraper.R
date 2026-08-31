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
               "javascript:", "mailto:", "tel:", "#")

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

# إضافة/تحديث معامل الصفحة في الرابط
with_page <- function(url, page) {
  if (grepl("[?&]page=", url)) {
    sub("([?&]page=)[^&]*", paste0("\\1", page), url)
  } else if (grepl("\\?", url)) {
    paste0(url, "&page=", page)
  } else {
    paste0(url, "?page=", page)
  }
}

# ------------------------------------------------------------- الجلب

# جلب صفحة مع إعادة المحاولة بتأخير متضاعف
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
        resp <- httr2::req_perform(req)
        httr2::resp_body_string(resp)
      } else {
        resp <- httr::GET(
          url,
          httr::user_agent(UA),
          httr::add_headers(`Accept-Language` = "ar,en;q=0.8"),
          httr::timeout(timeout)
        )
        httr::stop_for_status(resp)
        httr::content(resp, as = "text", encoding = "UTF-8")
      }
    }, error = function(e) {
      last_err <<- conditionMessage(e)
      NULL
    })
    if (!is.null(result)) return(result)
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

# استخراج روابط صفحات التفاصيل من صفحة القائمة، مع الحفاظ على الترتيب
extract_item_links <- function(html_txt, list_url) {
  doc <- rvest::read_html(html_txt)
  parts <- xml2::url_parse(list_url)
  list_path <- sub("/$", "", parts$path)
  host <- parts$server

  selectors <- c("a.article-link", ".article-item a", ".article-card a",
                 ".card a", ".decision-item a", ".list-item a",
                 "article a", ".results a", "a[href]")

  for (sel in selectors) {
    anchors <- rvest::html_elements(doc, sel)
    if (length(anchors) == 0) next
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
      # صفحة تفاصيل = مسار أعمق من مسار القائمة، أو مسار يحمل معرّفًا رقميًا
      deeper <- startsWith(path, paste0(list_path, "/"))
      has_id <- grepl("/[0-9]{2,}($|/|-)", path)
      if (!deeper && !has_id) next
      key <- sub("#.*$", "", abs_url)
      if (!(key %in% links)) links <- c(links, key)
    }
    if (length(links) > 0) return(links)
  }
  character(0)
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

# استخراج حقول عنصر واحد (نظام / لائحة / قرار) من صفحة التفاصيل
parse_detail <- function(html_txt, url) {
  doc <- rvest::read_html(html_txt)

  title <- first_text(doc, c("h1.article-title", ".article-title", "h1"))
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
                       list_only = FALSE,
                       out = NULL) {

  engine <- match.arg(engine)
  getter <- if (engine == "chromote") fetch_html_chromote else fetch_html

  if (is.null(url)) {
    if (!section %in% names(SECTIONS)) {
      stop('section لازم تكون "rules" أو "decisions"', call. = FALSE)
    }
    url <- paste0(BASE, SECTIONS[[section]])
  }
  if (is.null(out)) out <- sprintf("data/uqn_%s.json", section)

  max_pages <- if (all_pages) 1e6 else max(1, pages)

  # --- جمع الروابط من صفحات القائمة
  links <- character(0)
  page <- 1
  pages_done <- 0
  while (pages_done < max_pages) {
    target <- if (page == 1) url else with_page(url, page)
    html_txt <- getter(target)
    found <- extract_item_links(html_txt, url)
    fresh <- setdiff(found, links)
    message(sprintf("الصفحة %d: %d رابط (%d جديد)",
                    page, length(found), length(fresh)))
    if (length(fresh) == 0) break
    links <- c(links, fresh)
    if (limit > 0 && length(links) >= limit) {
      links <- links[seq_len(limit)]
      break
    }
    page <- page + 1
    pages_done <- pages_done + 1
    Sys.sleep(delay)
  }

  message(sprintf("إجمالي الروابط: %d", length(links)))

  if (list_only) return(links)

  if (length(links) == 0) {
    stop('لم يُعثر على روابط. جرّب engine = "chromote"', call. = FALSE)
  }

  # --- سحب صفحات التفاصيل
  items <- vector("list", length(links))
  for (i in seq_along(links)) {
    link <- links[i]
    record <- tryCatch({
      rec <- parse_detail(getter(link), link)
      rec$order <- i
      message(sprintf("[%d/%d] %s", i, length(links),
                      if (is.na(rec$title)) link else rec$title))
      rec
    }, error = function(e) {
      message(sprintf("[%d/%d] فشل %s : %s", i, length(links),
                      link, conditionMessage(e)))
      list(url = link, order = i, error = conditionMessage(e))
    })
    items[[i]] <- record
    Sys.sleep(delay)
  }

  # --- الحفظ في JSON
  out_dir <- dirname(out)
  if (nzchar(out_dir) && !dir.exists(out_dir)) {
    dir.create(out_dir, recursive = TRUE)
  }

  payload <- list(
    source_url = url,
    section    = section,
    scraped_at = format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"),
    count      = length(items),
    items      = items
  )

  json <- jsonlite::toJSON(payload, auto_unbox = TRUE, pretty = TRUE,
                           null = "null", na = "null")
  con <- file(out, open = "w", encoding = "UTF-8")
  on.exit(close(con), add = TRUE)
  writeLines(jsonlite::prettify(json), con, useBytes = TRUE)

  message(sprintf("تم الحفظ في %s (%d عنصر)", out, length(items)))
  invisible(items)
}
