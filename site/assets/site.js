/* Top 10 Everything — catalog browser.
   Data is injected as window.CATALOG by data/catalog.js. */
(function () {
  "use strict";

  const data = window.CATALOG;
  if (!data) return;

  const REPO = data.meta.repo;
  const $ = (id) => document.getElementById(id);
  const number = new Intl.NumberFormat("en-GB");

  function h(tag, attrs, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const key of Object.keys(attrs)) {
        const value = attrs[key];
        if (value === null || value === undefined) continue;
        if (key === "class") node.className = value;
        else if (key === "text") node.textContent = value;
        else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
        else node.setAttribute(key, value);
      }
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined) continue;
      node.append(child.nodeType ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return String(iso);
    return date.toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "numeric" });
  }

  function fmtNumber(value) {
    if (value === null || value === undefined) return "—";
    if (typeof value !== "number") return String(value);
    return new Intl.NumberFormat("en-GB", { maximumFractionDigits: 3 }).format(value);
  }

  function titleCase(value) {
    if (!value) return "—";
    return String(value).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function badge(label, variant) {
    return h("span", { class: "badge " + (variant || "neutral"), text: titleCase(label) });
  }

  const categoryName = new Map(data.categories.map((c) => [c.id, c.name]));

  /* ------------------------------------------------------------- hero */

  function renderHero() {
    const totals = data.meta.totals;
    const stats = [
      [totals.categories, "categories"],
      [totals.topics, "topics"],
      [totals.sources, "sources"],
      [totals.methods, "ranking methods"],
      [totals.rankings, "proven rankings"],
    ];
    const host = $("hero-stats");
    for (const [value, label] of stats) {
      host.append(
        h("div", { class: "stat" },
          h("span", { class: "stat-value", text: number.format(value) }),
          h("span", { class: "stat-label", text: label })
        )
      );
    }
    $("generated").textContent =
      "Catalog generated " + fmtDate(data.meta.generated_at) +
      " · rankings " + fmtDate(data.meta.ranking_generated_at) +
      " · metadata CC0 1.0";
    $("repo-link").href = "https://github.com/" + REPO;
  }

  /* --------------------------------------------------------- rankings */

  function renderRankings() {
    const host = $("ranking-grid");
    for (const ranking of data.rankings) {
      const card = h("button", { class: "ranking-card", type: "button", onclick: () => openRanking(ranking) },
        h("div", { class: "rc-top" },
          h("span", { class: "rc-cat", text: categoryName.get(ranking.category) || ranking.category })
        ),
        h("h3", { text: ranking.topic_name }),
        h("p", { class: "rc-leader" }, "Leads with", h("strong", { text: ranking.ranking?.[0]?.name || "—" })),
        h("span", { class: "rc-method", text: ranking.method?.name || ranking.method?.id || "method" }),
        h("div", { class: "rc-foot" },
          h("span", { text: number.format(ranking.snapshot?.records_considered || 0) + " records considered" }),
          h("span", { text: (ranking.measure?.label || "measure") })
        )
      );
      host.append(card);
    }
  }

  const dialog = $("ranking-dialog");

  function openRanking(ranking) {
    $("dialog-kicker").textContent = categoryName.get(ranking.category) || "Worked ranking";
    $("dialog-title").textContent = ranking.topic_name;
    const body = $("dialog-body");
    body.replaceChildren();

    body.append(h("p", { class: "dialog-lede", text: ranking.question }));
    body.append(
      h("div", { class: "dialog-facts" },
        h("div", { class: "dialog-fact" }, h("span", { text: "Measure" }), h("strong", { text: ranking.measure?.label || "—" }), ranking.measure?.unit ? h("span", { class: "fact-note", text: ranking.measure.unit }) : null),
        h("div", { class: "dialog-fact" }, h("span", { text: "Records considered" }), h("strong", { text: number.format(ranking.snapshot?.records_considered || 0) })),
        h("div", { class: "dialog-fact" }, h("span", { text: "Retrieved" }), h("strong", { text: fmtDate(ranking.snapshot?.retrieved_at) }))
      )
    );

    const table = h("table", { class: "rank-table" },
      h("thead", null,
        h("tr", null, h("th", { text: "#" }), h("th", { text: "Entity" }), h("th", { text: ranking.measure?.label || "Value" }))
      )
    );
    const tbody = h("tbody");
    for (const row of ranking.ranking || []) {
      tbody.append(
        h("tr", null,
          h("td", { class: "num", text: row.rank }),
          h("td", { text: row.name }),
          h("td", { class: "val", text: fmtNumber(row.value) + (row.unit ? " " + row.unit : "") })
        )
      );
    }
    table.append(tbody);
    body.append(table);

    const snapshot = ranking.snapshot || {};
    body.append(
      h("div", { class: "dialog-section" },
        h("h3", { text: "Snapshot and provenance" }),
        h("p", {
          text: [
            snapshot.catalogue ? "Candidate set: " + snapshot.catalogue + "." : "",
            snapshot.records_missing_value ? number.format(snapshot.records_missing_value) + " records dropped for a missing value." : "",
            snapshot.tied_at_cut ? "Rank 10 is tied." : "No tie at the cut.",
            "Refresh after " + fmtDate(ranking.refresh_after) + ".",
          ].filter(Boolean).join(" ")
        })
      )
    );

    if (ranking.sources?.length) {
      const list = h("div", { class: "dialog-section" }, h("h3", { text: "Sources and licence status" }));
      for (const source of ranking.sources) {
        list.append(
          h("p", null,
            h("a", { href: source.official_url || "#", target: "_blank", rel: "noopener", text: source.name }),
            " — commercial use: " + titleCase(source.commercial_use) +
            "; verified " + titleCase(source.verification_result) +
            " " + fmtDate(source.last_checked) + "."
          )
        );
      }
      body.append(list);
    }

    if (ranking.caveats?.length) {
      const list = h("div", { class: "dialog-section" }, h("h3", { text: "Limitations that travel with this ranking" }));
      list.append(h("ul", null, ranking.caveats.map((caveat) => h("li", { text: caveat }))));
      body.append(list);
    }

    body.append(
      h("div", { class: "dialog-section" },
        h("h3", { text: "Reproduce it" }),
        h("p", null,
          "Generated by the open pipeline described in ",
          h("a", { href: "https://github.com/" + REPO + "/blob/main/docs/ingestion.md", text: "docs/ingestion.md" }),
          ". Run ",
          h("code", { text: "python -m pipeline.run --topic " + ranking.topic_id }),
          " to rebuild it from the cached snapshot. Raw output: ",
          h("a", { href: "https://github.com/" + REPO + "/blob/main/rankings/" + ranking.topic_id + ".json", text: "rankings/" + ranking.topic_id + ".json" }),
          "."
        )
      )
    );

    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  $("dialog-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });

  /* ------------------------------------------------------------ topics */

  const PAGE = 60;
  const topicState = { query: "", category: "", status: "", availability: "", shown: PAGE };
  const topicList = $("topic-list");
  const topicCount = $("topic-count");
  const topicMore = $("topic-more");
  const collator = new Intl.Collator("en", { sensitivity: "base", numeric: true });

  function topicMatches(topic) {
    if (topicState.category && topic.category !== topicState.category) return false;
    if (topicState.status && topic.status !== topicState.status) return false;
    if (topicState.availability && topic.availability !== topicState.availability) return false;
    if (!topicState.query) return true;
    const haystack = [
      topic.name, topic.id, topic.category_name, topic.method.name, topic.method.question,
      topic.method.metric, ...topic.subcategories, ...topic.sources.primary.map((s) => s.name),
      ...topic.sources.backup.map((s) => s.name),
    ].join(" ").toLowerCase();
    return topicState.query.toLowerCase().split(/\s+/).every((word) => haystack.includes(word));
  }

  function filteredTopics() {
    return data.topics.filter(topicMatches).sort((a, b) => collator.compare(a.name, b.name));
  }

  function topicRow(topic) {
    const primary = topic.sources.primary || [];
    const backup = topic.sources.backup || [];
    const side = h("div", { class: "topic-side" });

    if (primary.length || backup.length) {
      side.append(h("div", null,
        h("h4", { text: "Primary sources" }),
        primary.length
          ? primary.map((s) => h("div", { class: "source-mini" },
              h("a", {
                href: "#sources",
                onclick: (event) => {
                  event.preventDefault();
                  focusSource(s.name);
                },
                text: s.name,
              }),
              h("span", { class: "meta", text: [titleCase(s.access), titleCase(s.commercial)].filter(Boolean).join(" · ") })
            ))
          : h("p", { class: "source-mini", text: "No free primary source identified." })
      ));
      if (backup.length) {
        side.append(h("div", null,
          h("h4", { text: "Backup sources" }),
          backup.map((s) => h("div", { class: "source-mini" },
            h("a", {
              href: "#sources",
              onclick: (event) => {
                event.preventDefault();
                focusSource(s.name);
              },
              text: s.name,
            }),
            h("span", { class: "meta", text: [titleCase(s.access), titleCase(s.commercial)].filter(Boolean).join(" · ") })
          ))
        ));
      }
    } else {
      side.append(h("div", null, h("h4", { text: "Sources" }), h("p", { class: "source-mini", text: "No responsible free source identified." })));
    }

    side.append(h("div", null,
      h("h4", { text: "Refresh and coverage" }),
      h("p", { class: "topic-metric" },
        "Update " + titleCase(topic.frequency) + " · " +
        (topic.coverage.length ? topic.coverage.join(", ") : "coverage unspecified") + " · " +
        "licensing risk " + titleCase(topic.risk) + "."
      )
    ));

    const left = h("div", null,
      h("h4", { text: "The question it answers" }),
      h("p", { class: "topic-question", text: topic.method.question || "No ranking question recorded." }),
      h("p", { class: "topic-metric" }, h("strong", { text: "Measure: " }), topic.method.metric || "—"),
      h("p", { class: "topic-metric" },
        h("strong", { text: "Method: " }),
        (topic.method.name || topic.method.id || "—") +
        (topic.method.subjectivity ? " · " + titleCase(topic.method.subjectivity) : "")
      )
    );
    if (topic.subcategories.length) {
      left.append(h("h4", { text: "Subcategories (" + topic.subcategories.length + ")" }));
      left.append(h("div", { class: "chips" },
        topic.subcategories.slice(0, 24).map((sub) => h("span", { class: "chip", text: sub })),
        topic.subcategories.length > 24 ? h("span", { class: "chip", text: "+" + (topic.subcategories.length - 24) + " more" }) : null
      ));
    }
    if (topic.notes.length) {
      left.append(h("h4", { text: "Notes and caveats", style: "margin-top:14px" }));
      left.append(h("ul", { class: "topic-notes" }, topic.notes.map((note) => h("li", { text: note }))));
    }

    return h("details", { class: "topic" },
      h("summary", null,
        h("span", { class: "caret", "aria-hidden": "true", text: "▶" }),
        h("span", { class: "topic-name" }, topic.name, h("small", { text: topic.id })),
        h("span", { class: "topic-method", text: topic.method.name || topic.method.id || "" }),
        h("span", { class: "topic-badges" },
          badge(topic.status, topic.status),
          badge(topic.availability, topic.availability)
        )
      ),
      h("div", { class: "topic-body" }, left, side)
    );
  }

  function renderTopics() {
    const matches = filteredTopics();
    const visible = matches.slice(0, topicState.shown);
    topicList.replaceChildren(...visible.map(topicRow));
    const total = data.topics.length;
    topicCount.textContent = matches.length === total
      ? "Showing " + visible.length + " of " + number.format(total) + " topics."
      : "Showing " + visible.length + " of " + number.format(matches.length) + " matching topics (" + number.format(total) + " total).";
    topicMore.hidden = matches.length <= topicState.shown;
    topicMore.textContent = "Show " + Math.min(PAGE, matches.length - topicState.shown) + " more topics";
  }

  function resetTopics() {
    topicState.query = "";
    topicState.category = "";
    topicState.status = "";
    topicState.availability = "";
    topicState.shown = PAGE;
    $("topic-search").value = "";
    $("topic-category").value = "";
    $("topic-status").value = "";
    $("topic-availability").value = "";
    renderTopics();
  }

  function wireTopics() {
    const select = $("topic-category");
    data.categories
      .slice()
      .sort((a, b) => collator.compare(a.name, b.name))
      .forEach((category) => select.append(h("option", { value: category.id, text: category.name + " (" + category.topic_count + ")" })));

    $("topic-search").addEventListener("input", (event) => {
      topicState.query = event.target.value.trim();
      topicState.shown = PAGE;
      renderTopics();
    });
    select.addEventListener("change", (event) => { topicState.category = event.target.value; topicState.shown = PAGE; renderTopics(); });
    $("topic-status").addEventListener("change", (event) => { topicState.status = event.target.value; topicState.shown = PAGE; renderTopics(); });
    $("topic-availability").addEventListener("change", (event) => { topicState.availability = event.target.value; topicState.shown = PAGE; renderTopics(); });
    $("topic-reset").addEventListener("click", resetTopics);
    topicMore.addEventListener("click", () => { topicState.shown += PAGE; renderTopics(); });
    renderTopics();
  }

  /* ----------------------------------------------------------- sources */

  const sourceState = { query: "", access: "", commercial: "" };
  const sourceList = $("source-list");
  const sourceCount = $("source-count");

  function sourceMatches(source) {
    if (sourceState.access && source.access !== sourceState.access) return false;
    if (sourceState.commercial && source.commercial !== sourceState.commercial) return false;
    if (!sourceState.query) return true;
    const haystack = [
      source.name, source.organization, source.id, source.access, source.commercial,
      source.license, source.auth, source.limits, ...source.caveats,
    ].join(" ").toLowerCase();
    return sourceState.query.toLowerCase().split(/\s+/).every((word) => haystack.includes(word));
  }

  function verificationVariant(result) {
    if (result === "ok") return "allowed";
    if (result === "auth_required" || result === "rate_limited") return "free_key";
    if (result === "forbidden") return "partial";
    return "unsupported";
  }

  function sourceRow(source) {
    const topics = source.primary_topics + source.backup_topics;
    return h("details", { class: "source" },
      h("summary", null,
        h("span", { class: "caret", "aria-hidden": "true", text: "▶" }),
        h("span", { class: "source-name" }, source.name, h("small", { text: source.organization || source.id })),
        h("span", { class: "topic-badges" },
          badge(source.access, source.access),
          badge(source.commercial, source.commercial),
          badge(source.verification, verificationVariant(source.verification)),
          h("span", { class: "source-meta", text: topics + " topics" })
        )
      ),
      h("div", { class: "source-body" },
        h("div", null,
          h("h4", { text: "Access and limits" }),
          h("p", { text: source.limits || "No free-tier limit recorded." }),
          h("p", null,
            h("a", { href: source.url || "https://github.com/" + REPO, target: "_blank", rel: "noopener", text: "Official site ↗" }),
            source.docs ? h("span", null, " · ", h("a", { href: source.docs, target: "_blank", rel: "noopener", text: "API docs ↗" })) : null
          ),
          h("h4", { text: "Licence", style: "margin-top:14px" }),
          h("p", {
            text: (source.license || "Licence not named") +
              " · commercial use " + (source.commercial || "unknown").replace(/_/g, " ") +
              (source.attribution ? " · attribution required" : " · no attribution requirement recorded") + ".",
          })
        ),
        h("div", null,
          h("h4", { text: "Verification" }),
          h("p", { text: titleCase(source.verification) + " on " + fmtDate(source.checked) + ". Reachability only — not legal clearance." }),
          h("h4", { text: "Catalog usage", style: "margin-top:14px" }),
          h("p", { text: source.primary_topics + " primary · " + source.backup_topics + " backup topic assignments. Update cadence: " + titleCase(source.frequency) + "." }),
          source.reference_only ? h("p", { text: "Reference only: catalogued for methodology comparison, not redistribution." }) : null,
          source.caveats.length ? h("ul", { class: "topic-notes" }, source.caveats.map((caveat) => h("li", { text: caveat }))) : null
        )
      )
    );
  }

  function renderSources() {
    const matches = data.sources.filter(sourceMatches);
    sourceList.replaceChildren(...matches.map(sourceRow));
    sourceCount.textContent = sourceState.query || sourceState.access || sourceState.commercial
      ? "Showing " + number.format(matches.length) + " of " + number.format(data.sources.length) + " sources."
      : "Showing all " + number.format(matches.length) + " sources.";
  }

  function focusSource(name) {
    sourceState.query = name;
    $("source-search").value = name;
    renderSources();
    document.getElementById("sources").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function wireSources() {
    $("source-search").addEventListener("input", (event) => { sourceState.query = event.target.value.trim(); renderSources(); });
    $("source-access").addEventListener("change", (event) => { sourceState.access = event.target.value; renderSources(); });
    $("source-commercial").addEventListener("change", (event) => { sourceState.commercial = event.target.value; renderSources(); });
    renderSources();
  }

  /* ----------------------------------------------------------- methods */

  function renderMethods() {
    const host = $("method-grid");
    for (const method of data.methods) {
      host.append(
        h("article", { class: "method-card" },
          h("div", { class: "method-top" },
            h("h3", { text: method.name }),
            h("span", { class: "method-tag", text: method.subjectivity || method.basis || "" })
          ),
          h("p", { text: method.description }),
          method.criteria.length ? h("ul", { class: "method-criteria" }, method.criteria.slice(0, 3).map((item) => h("li", { text: item }))) : null,
          h("div", { class: "method-foot" },
            h("span", { text: method.basis ? method.basis.replace(/_/g, " ") : method.id }),
            h("span", { text: method.human_review ? "human review required" : "automatable" })
          )
        )
      );
    }
  }

  /* ------------------------------------------------------ unsupported */

  function renderUnsupported() {
    const host = $("unsupported-chips");
    for (const topic of data.unsupported?.topics || []) {
      host.append(h("span", { class: "chip", title: topic.reason, text: topic.topic_name + " · " + topic.category }));
    }
  }

  /* -------------------------------------------------------------- init */

  renderHero();
  renderRankings();
  wireTopics();
  wireSources();
  renderMethods();
  renderUnsupported();
})();
