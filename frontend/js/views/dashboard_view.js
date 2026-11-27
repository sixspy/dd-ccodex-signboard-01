window.SB_VIEWS = window.SB_VIEWS || {};
window.SB_VIEWS["dashboard-view"] = {
  template: `
  <div class="panel">
    <h2>总览</h2>
    <p class="lead">{{ meta.skeleton || "加载中…" }}</p>
    <div class="stats">
      <div class="stat" v-for="s in cards" :key="s.k">
        <b :style="s.alert ? 'color:var(--danger)' : ''">{{ s.v }}</b><span>{{ s.l }}</span>
      </div>
    </div>
    <p class="lead" style="margin-top:14px;color:var(--muted)">
      signboard-01：风险≥4 分区正式上屏须附场控单号，缺号整笔拒写；同屏并发发布互斥，败方正式零增。
    </p>
  </div>`,
  data() { return { meta: {}, cards: [] }; },
  async mounted() {
    const d = await SB.api("/api/dashboard");
    this.meta = d;
    this.cards = [
      { k: "screens", l: "屏幕总数", v: d.screens },
      { k: "online", l: "在线屏幕", v: d.online_screens },
      { k: "assets", l: "可播素材", v: d.ready_assets },
      { k: "pubs", l: "正式发布", v: d.official_publications },
      { k: "shadows", l: "待升正影子", v: d.open_shadows },
      { k: "high", l: "高风险分区(≥4)", v: d.high_risk_zones, alert: d.high_risk_zones > 0 },
      { k: "ticket", l: "待补票影子", v: d.ticket_pending_shadows, alert: d.ticket_pending_shadows > 0 },
      { k: "ov", l: "生效覆盖", v: d.active_overrides },
    ];
  }
};
