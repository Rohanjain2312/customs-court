import { hierarchy, tree as d3tree, type HierarchyPointNode } from "d3-hierarchy";
import { select, type Selection } from "d3-selection";
import { linkHorizontal } from "d3-shape";
import "d3-transition";
import { zoom as d3zoom, zoomIdentity, type ZoomBehavior } from "d3-zoom";
import { useCallback, useEffect, useRef, useState } from "react";
import type { CourtApi } from "../lib/api";
import { digitsOf, formatHts, levelName } from "../lib/hts";
import type { FocusEntry } from "../lib/runState";
import type { NodeState } from "../lib/types";

interface TNode {
  key: string;
  code: string;
  digits: string;
  description: string;
  isLeaf: boolean;
  children: TNode[] | null;
  error: boolean;
  range?: [number, number];
}

interface Props {
  api: CourtApi;
  focus: Record<string, FocusEntry>;
  follow: { code: string; seq: number } | null;
  resetKey: string | number;
  onPick?: (code: string, description: string) => void;
  pickHint?: string | null;
}

interface Tip {
  x: number;
  y: number;
  title: string;
  state: NodeState | null;
  body: string;
}

const ROW_H = 26;
const COL_W = 330;
const MAX_ANIMATED = 350;
const STATE_TAG: Record<NodeState, string> = {
  visited: "visited",
  candidate: "candidate",
  rejected: "rejected",
  chosen: "chosen",
  overruled: "overruled",
};

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s;
}

type LinkDatum = { source: [number, number]; target: [number, number]; hot: boolean; key: string };

export function HtsTree({ api, focus, follow, resetKey, onPick, pickHint }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const layerRef = useRef<Selection<SVGGElement, unknown, null, undefined> | null>(null);
  const zoomRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const rootRef = useRef<TNode>({ key: "root", code: "", digits: "", description: "Harmonized Tariff Schedule", isLeaf: false, children: null, error: false });
  const expandedRef = useRef<Set<string>>(new Set(["root"]));
  const loadingRef = useRef<Map<string, Promise<void>>>(new Map());
  const posRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const focusRef = useRef(focus);
  const queueRef = useRef<Promise<unknown>>(Promise.resolve());
  const rafRef = useRef<number | null>(null);
  const onPickRef = useRef(onPick);
  const [tip, setTip] = useState<Tip | null>(null);
  const [followOn, setFollowOn] = useState(true);
  const followOnRef = useRef(followOn);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [nodeCount, setNodeCount] = useState(0);

  focusRef.current = focus;
  onPickRef.current = onPick;
  followOnRef.current = followOn;

  // ---- data loading -------------------------------------------------------

  const load = useCallback(
    (node: TNode): Promise<void> => {
      if (node.children !== null || node.isLeaf) return Promise.resolve();
      const inflight = loadingRef.current.get(node.key);
      if (inflight) return inflight;
      const p = api
        .htsNode(node.code)
        .then((res) => {
          const seen = new Set<string>();
          node.children = res.children.map((c, i) => {
            const d = digitsOf(c.code);
            let key = `${node.key}/${d || `i${i}`}`;
            if (seen.has(key)) key = `${key}~${i}`;
            seen.add(key);
            return {
              key,
              code: c.code,
              digits: d,
              description: c.description,
              isLeaf: c.is_leaf,
              children: c.is_leaf ? [] : null,
              error: false,
              range: c.range,
            };
          });
          setLoadError(null);
        })
        .catch(() => {
          node.error = true;
          node.children = null;
          setLoadError("Could not load part of the tariff tree.");
        })
        .finally(() => loadingRef.current.delete(node.key));
      loadingRef.current.set(node.key, p);
      return p;
    },
    [api],
  );

  /** Expands the path from the root down to the deepest node matching `code`. Returns that node's key. */
  const reveal = useCallback(
    async (code: string): Promise<string | null> => {
      const target = digitsOf(code);
      if (!target) return null;
      let cur = rootRef.current;
      await load(cur);
      // A node is opened only when one of its children leads toward the target, so an
      // unknown code never unfolds a whole chapter.
      const open: string[] = [];
      for (let guard = 0; guard < 12; guard++) {
        const kids = cur.children ?? [];
        let best: TNode | null = null;
        for (const k of kids) {
          if (k.digits && k.digits !== cur.digits && target.startsWith(k.digits) && (!best || k.digits.length > best.digits.length)) best = k;
        }
        if (!best && target.length >= 2) {
          // Sections carry a chapter range instead of digits.
          const ch = Number(target.slice(0, 2));
          best = kids.find((k) => k.range && ch >= k.range[0] && ch <= k.range[1]) ?? null;
        }
        if (!best) {
          // Some HTS rows are un-numbered indents; look one level inside them.
          const indents = kids.filter((k) => !k.isLeaf && (!k.digits || k.digits === cur.digits)).slice(0, 6);
          for (const ind of indents) {
            await load(ind);
            if ((ind.children ?? []).some((c) => c.digits && target.startsWith(c.digits))) {
              best = ind;
              break;
            }
          }
        }
        if (!best) break;
        open.push(cur.key);
        if (best.digits === target) {
          cur = best;
          break;
        }
        await load(best);
        cur = best;
      }
      for (const k of open) expandedRef.current.add(k);
      return cur.key;
    },
    [load],
  );

  // ---- drawing ------------------------------------------------------------

  const draw = useCallback(() => {
    const layer = layerRef.current;
    if (!layer) return;
    const expanded = expandedRef.current;
    const focusMap = focusRef.current;
    const root = hierarchy<TNode>(rootRef.current, (d) => (expanded.has(d.key) && d.children ? d.children : null));
    const laid = d3tree<TNode>()
      .nodeSize([ROW_H, COL_W])
      .separation((a, b) => (a.parent === b.parent ? 1 : 1.3))(root);
    const nodes = laid.descendants();
    setNodeCount(nodes.length);

    // Nodes on the way to any node with a state are "hot" so their links glow.
    const hot = new Set<string>();
    for (const n of nodes) {
      if (n.data.digits && focusMap[n.data.digits]) {
        for (let p: HierarchyPointNode<TNode> | null = n; p; p = p.parent) hot.add(p.data.key);
      }
    }

    const animate = nodes.length <= MAX_ANIMATED;
    const dur = animate ? 380 : 0;
    const pos = posRef.current;

    const links: LinkDatum[] = laid.links().map((l) => ({
      key: l.target.data.key,
      source: [l.source.y, l.source.x],
      target: [l.target.y, l.target.x],
      hot: hot.has(l.target.data.key),
    }));
    const linkGen = linkHorizontal<LinkDatum, [number, number]>()
      .source((d) => d.source)
      .target((d) => d.target);

    const linkSel = layer
      .select<SVGGElement>("g.links")
      .selectAll<SVGPathElement, LinkDatum>("path")
      .data(links, (d) => d.key);
    linkSel.exit().remove();
    const linkEnter = linkSel
      .enter()
      .append("path")
      .attr("class", "tree-link")
      .attr("d", (d) => {
        const from = pos.get(d.key.slice(0, d.key.lastIndexOf("/"))) ?? { x: d.source[1], y: d.source[0] };
        const p: [number, number] = [from.y, from.x];
        return linkGen({ ...d, source: p, target: p });
      });
    const linkAll = linkEnter.merge(linkSel).classed("hot", (d) => d.hot);
    if (animate) linkAll.transition().duration(dur).attr("d", (d) => linkGen(d));
    else linkAll.attr("d", (d) => linkGen(d));

    const nodeSel = layer
      .select<SVGGElement>("g.nodes")
      .selectAll<SVGGElement, HierarchyPointNode<TNode>>("g.tree-node")
      .data(nodes, (d) => d.data.key);
    nodeSel.exit().remove();

    const enter = nodeSel
      .enter()
      .append("g")
      .attr("class", "tree-node")
      .attr("data-testid", "tree-node")
      .attr("tabindex", 0)
      .attr("role", "button")
      .attr("transform", (d) => {
        const parentKey = d.parent?.data.key;
        const from = (parentKey && pos.get(parentKey)) || { x: d.x, y: d.y };
        return `translate(${from.y},${from.x})`;
      });
    enter.append("circle").attr("class", "halo").attr("r", 11);
    enter.append("circle").attr("class", "dot").attr("r", 5);
    enter.append("path").attr("class", "mark");
    const label = enter.append("text").attr("class", "label").attr("x", 12).attr("dy", "0.34em");
    label.append("tspan").attr("class", "caret");
    label.append("tspan").attr("class", "code");
    label.append("tspan").attr("class", "desc").attr("dx", 6);
    label.append("tspan").attr("class", "tag").attr("dx", 8);

    const all = enter.merge(nodeSel);
    all.each(function (d) {
      const g = select(this);
      const n = d.data;
      const f = n.digits ? focusMap[n.digits] : undefined;
      const state = f?.state ?? null;
      const isRoot = n.key === "root";
      const isOpen = expanded.has(n.key) && !!n.children && n.children.length > 0;
      const isSection = n.code.startsWith("S-");
      const code = isRoot ? "HTS" : isSection ? `Sec. ${n.code.slice(2)}` : formatHts(n.code) || "·";
      g.attr("data-code", isRoot || isSection ? "" : formatHts(n.code))
        .attr("data-state", state ?? "none")
        .attr("data-open", isOpen ? "true" : "false")
        .attr("data-level", isRoot ? "root" : levelName(n.code).toLowerCase().replace(/\s+/g, "-"))
        .attr(
          "aria-label",
          `${isRoot ? "Tariff schedule root" : isSection ? code : `${levelName(n.code)} ${code}`}: ${n.description}.${state ? ` State: ${state}.` : ""}${
            n.isLeaf ? "" : isOpen ? " Expanded." : " Collapsed."
          }`,
        )
        .attr("aria-expanded", n.isLeaf ? null : isOpen ? "true" : "false");
      g.select("circle.dot").attr("r", state === "chosen" ? 8 : state === "candidate" ? 6.5 : isRoot ? 7 : 5);
      // Shape cue so state never depends on colour alone.
      g.select("path.mark").attr(
        "d",
        state === "rejected" || state === "overruled"
          ? "M-4,-4L4,4M-4,4L4,-4"
          : state === "chosen"
            ? "M0,-3.5L1,-1L3.5,-1L1.5,0.8L2.3,3.4L0,2L-2.3,3.4L-1.5,0.8L-3.5,-1L-1,-1Z"
            : "",
      );
      g.select("tspan.caret").text(n.isLeaf || isRoot ? "" : isOpen ? "▾ " : "▸ ");
      g.select("tspan.code").text(code);
      // Open nodes have children to their right, so their labels stay short.
      const descLen = isOpen ? 16 : d.depth <= 1 ? 44 : 34;
      g.select("tspan.desc").text(truncate(isSection ? n.description.replace(/^Section [IVXL]+: /, "") : n.description, descLen));
      g.select("tspan.tag").text(state && state !== "visited" && !isOpen ? STATE_TAG[state] : "");
    });

    if (animate) all.transition().duration(dur).attr("transform", (d) => `translate(${d.y},${d.x})`);
    else all.attr("transform", (d) => `translate(${d.y},${d.x})`);

    pos.clear();
    for (const n of nodes) pos.set(n.data.key, { x: n.x, y: n.y });
  }, []);

  const scheduleDraw = useCallback(() => {
    if (rafRef.current !== null) return;
    rafRef.current = window.requestAnimationFrame(() => {
      rafRef.current = null;
      draw();
    });
  }, [draw]);

  const centerOn = useCallback((key: string, minScale = 0.85) => {
    const svg = svgRef.current;
    const z = zoomRef.current;
    const p = posRef.current.get(key);
    if (!svg || !z || !p) return;
    const { width, height } = svg.getBoundingClientRect();
    const current = (svg as unknown as { __zoom?: { k: number } }).__zoom?.k ?? 1;
    const k = Math.max(current, minScale);
    // Keep the node a little left of centre so its label has room.
    const t = zoomIdentity.translate(width * 0.38, height / 2).scale(k).translate(-p.y, -p.x);
    select(svg).transition().duration(650).call(z.transform, t);
  }, []);

  const fitAll = useCallback(() => {
    const svg = svgRef.current;
    const z = zoomRef.current;
    if (!svg || !z || posRef.current.size === 0) return;
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const p of posRef.current.values()) {
      minX = Math.min(minX, p.x);
      maxX = Math.max(maxX, p.x);
      minY = Math.min(minY, p.y);
      maxY = Math.max(maxY, p.y);
    }
    const { width, height } = svg.getBoundingClientRect();
    const w = maxY - minY + COL_W + 40;
    const h = maxX - minX + ROW_H * 2;
    const k = Math.max(0.15, Math.min(1.4, Math.min(width / w, height / h)));
    const t = zoomIdentity
      .translate(width / 2, height / 2)
      .scale(k)
      .translate(-(minY + (maxY - minY + COL_W) / 2), -(minX + maxX) / 2);
    select(svg).transition().duration(500).call(z.transform, t);
  }, []);

  // ---- setup --------------------------------------------------------------

  useEffect(() => {
    const svgEl = svgRef.current;
    if (!svgEl) return;
    const svg = select(svgEl);
    svg.selectAll("*").remove();
    const defs = svg.append("defs");
    const glow = defs.append("filter").attr("id", "cc-glow").attr("x", "-100%").attr("y", "-100%").attr("width", "300%").attr("height", "300%");
    glow.append("feGaussianBlur").attr("stdDeviation", 3.2).attr("result", "blur");
    const merge = glow.append("feMerge");
    merge.append("feMergeNode").attr("in", "blur");
    merge.append("feMergeNode").attr("in", "SourceGraphic");

    const layer = svg.append("g").attr("class", "layer");
    layer.append("g").attr("class", "links");
    layer.append("g").attr("class", "nodes");
    layerRef.current = layer;

    const z = d3zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.12, 3])
      .on("zoom", (e: { transform: { toString(): string } }) => {
        layer.attr("transform", e.transform.toString());
      });
    zoomRef.current = z;
    svg.call(z).on("dblclick.zoom", null);
    const { height } = svgEl.getBoundingClientRect();
    svg.call(z.transform, zoomIdentity.translate(40, height / 2).scale(0.9));

    // Delegated events keep handlers off each node.
    const activate = (target: EventTarget | null) => {
      const g = (target as Element | null)?.closest?.("g.tree-node");
      if (!g) return;
      const d = select<Element, HierarchyPointNode<TNode>>(g).datum();
      const n = d.data;
      if (n.key !== "root" && n.digits) onPickRef.current?.(n.code, n.description);
      if (n.isLeaf || n.key === "root") return;
      if (expandedRef.current.has(n.key)) {
        expandedRef.current.delete(n.key);
        scheduleDraw();
      } else {
        void load(n).then(() => {
          expandedRef.current.add(n.key);
          draw();
          window.setTimeout(() => centerOn(n.key, 0), 50);
        });
      }
    };
    svg.on("click.node", (e: MouseEvent) => activate(e.target));
    svg.on("keydown.node", (e: KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        activate(e.target);
      }
    });
    const showTip = (e: MouseEvent | FocusEvent) => {
      const g = (e.target as Element | null)?.closest?.("g.tree-node");
      const wrap = wrapRef.current;
      if (!g || !wrap) return;
      const d = select<Element, HierarchyPointNode<TNode>>(g).datum();
      const n = d.data;
      const f = n.digits ? focusRef.current[n.digits] : undefined;
      const rect = wrap.getBoundingClientRect();
      const gr = g.getBoundingClientRect();
      setTip({
        x: Math.min(gr.left - rect.left + 14, rect.width - 300),
        y: gr.bottom - rect.top + 6,
        title: n.key === "root" ? "Harmonized Tariff Schedule" : n.code.startsWith("S-") ? `Section ${n.code.slice(2)}` : `${levelName(n.code)} ${formatHts(n.code)}`,
        state: f?.state ?? null,
        body: f?.reason ? `${n.description}\n\n${f.reason}` : n.description,
      });
    };
    svg.on("mouseover.tip", showTip);
    svg.on("focusin.tip", showTip);
    svg.on("mouseout.tip", () => setTip(null));
    svg.on("focusout.tip", () => setTip(null));
    svg.on("mousedown.tip", () => setTip(null));

    void load(rootRef.current).then(() => {
      draw();
    });
    return () => {
      svg.on(".node", null).on(".tip", null).on(".zoom", null);
      if (rafRef.current !== null) window.cancelAnimationFrame(rafRef.current);
    };
  }, [load, draw, scheduleDraw, centerOn]);

  // Redraw when node states change.
  useEffect(() => {
    scheduleDraw();
  }, [focus, scheduleDraw]);

  // Follow the hearing: expand to each focused code in order.
  useEffect(() => {
    if (!follow) return;
    const code = follow.code;
    queueRef.current = queueRef.current
      .then(() => reveal(code))
      .then((key) => {
        draw();
        if (key && followOnRef.current) window.setTimeout(() => centerOn(key), 30);
      })
      .catch(() => undefined);
  }, [follow, reveal, draw, centerOn]);

  // New exhibit: fold the tree back to chapters.
  const firstReset = useRef(true);
  useEffect(() => {
    if (firstReset.current) {
      firstReset.current = false;
      return;
    }
    expandedRef.current = new Set(["root"]);
    draw();
    const svg = svgRef.current;
    const z = zoomRef.current;
    if (svg && z) {
      const { height } = svg.getBoundingClientRect();
      select(svg).transition().duration(400).call(z.transform, zoomIdentity.translate(40, height / 2).scale(0.9));
    }
  }, [resetKey, draw]);

  const zoomBy = (factor: number) => {
    const svg = svgRef.current;
    const z = zoomRef.current;
    if (svg && z) select(svg).transition().duration(250).call(z.scaleBy, factor);
  };

  const collapse = () => {
    expandedRef.current = new Set(["root"]);
    draw();
    window.setTimeout(() => centerOn("root", 0.9), 30);
  };

  return (
    <div ref={wrapRef} className="relative h-full w-full overflow-hidden">
      <svg
        ref={svgRef}
        data-testid="tree-svg"
        className="tree-svg h-full w-full cursor-grab active:cursor-grabbing"
        role="tree"
        aria-label="Harmonized Tariff Schedule tree. Drag to pan, scroll to zoom. Tab to a node and press Enter to open it."
      />

      <div className="absolute right-3 top-3 flex flex-col gap-1.5" role="toolbar" aria-label="Tree controls">
        <button type="button" className="tree-btn" onClick={() => zoomBy(1.3)} aria-label="Zoom in">
          +
        </button>
        <button type="button" className="tree-btn" onClick={() => zoomBy(1 / 1.3)} aria-label="Zoom out">
          −
        </button>
        <button type="button" className="tree-btn text-[0.7rem]" onClick={fitAll} aria-label="Fit the whole tree in view">
          Fit
        </button>
        <button type="button" className="tree-btn text-[0.7rem]" onClick={collapse} aria-label="Fold the tree back to chapters">
          Fold
        </button>
        <button
          type="button"
          className={`tree-btn text-[0.7rem] ${followOn ? "!border-brass-400 !text-brass-300" : ""}`}
          onClick={() => setFollowOn((v) => !v)}
          aria-pressed={followOn}
          aria-label="Follow the hearing on the tree"
          title="Follow the hearing"
        >
          {followOn ? "Follow" : "Free"}
        </button>
      </div>

      <div className="pointer-events-none absolute bottom-0 left-0 right-0 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-brass-900/70 bg-ink-950/90 px-3 py-1.5 text-[0.72rem] text-parchment-400">
        <LegendItem cls="visited" label="Visited" />
        <LegendItem cls="candidate" label="Candidate" />
        <LegendItem cls="rejected" label="Rejected" />
        <LegendItem cls="chosen" label="Chosen" />
        <LegendItem cls="overruled" label="Overruled" />
        <span className="ml-auto font-mono text-parchment-500">{nodeCount} nodes</span>
      </div>

      {pickHint ? (
        <div className="pointer-events-none absolute left-3 top-3 rounded border border-brass-500/60 bg-walnut-900/90 px-3 py-1.5 text-sm text-brass-200">
          {pickHint}
        </div>
      ) : null}

      {loadError ? (
        <div role="alert" className="absolute left-3 top-12 rounded border border-verdict-red/60 bg-walnut-900/95 px-3 py-1.5 text-sm text-verdict-red">
          {loadError}
        </div>
      ) : null}

      {tip ? (
        <div
          role="tooltip"
          className="pointer-events-none absolute z-20 max-w-[18rem] whitespace-pre-line rounded border border-brass-600/70 bg-ink-950/95 px-3 py-2 text-[0.8rem] leading-snug text-parchment-100 shadow-brass"
          style={{ left: Math.max(4, tip.x), top: tip.y }}
        >
          <div className="mb-1 flex items-center gap-2">
            <span className="font-mono text-brass-300">{tip.title}</span>
            {tip.state ? <span className={`state-chip state-${tip.state}`}>{tip.state}</span> : null}
          </div>
          {tip.body}
        </div>
      ) : null}
    </div>
  );
}

function LegendItem({ cls, label }: { cls: NodeState; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <svg width="14" height="14" viewBox="-7 -7 14 14" aria-hidden="true" className={`legend-dot legend-${cls}`}>
        <circle r="4.5" />
        {cls === "rejected" || cls === "overruled" ? <path d="M-3,-3L3,3M-3,3L3,-3" /> : null}
      </svg>
      {label}
    </span>
  );
}
