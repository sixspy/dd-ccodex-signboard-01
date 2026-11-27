window.SB_VIEWS = window.SB_VIEWS || {};
window.SB_VIEWS["evaluate-view"] = {
  template: `
  <div class="panel">
    <h2>在线求值</h2>
    <p class="lead">给定屏幕与时刻，计算应播内容（覆盖优先）。仅认真式发布行，未升正影子一律不参与求值。</p>
    <div class="row-form">
      <input v-model.number="screen_id" type="number" placeholder="屏幕ID" />
      <input v-model="now_hm" placeholder="HH:MM" />
      <input v-model="weekday" placeholder="星期1-7" />
      <button class="primary" @click="run">求值</button>
    </div>
    <div v-if="result" class="row-form" style="margin-top:10px">
      <span class="badge" :class="result.source==='publication' ? '' : 'warn'">来源：{{ sourceLabel }}</span>
      <span v-if="result.source==='publication'" class="badge" :class="result.field_ticket_no ? '' : 'warn'">
        场控单号：{{ result.field_ticket_no || "低风险免票" }}
      </span>
      <span v-if="result.source==='empty'" class="badge bad">无正式发布（影子未升正不算上屏）</span>
    </div>
    <pre style="white-space:pre-wrap;background:#0d1828;padding:12px;border-radius:10px;">{{ resultText }}</pre>
    <p class="err" v-if="error">{{ error }}</p>
  </div>`,
  data() {
    return {
      screen_id: 1, now_hm: "10:30", weekday: "1",
      resultText: "", result: null, error: ""
    };
  },
  computed: {
    sourceLabel() {
      return { publication: "正式发布", override: "单屏覆盖", empty: "空屏" }[this.result?.source] || this.result?.source;
    }
  },
  methods: {
    async run() {
      this.error = "";
      try {
        const r = await SB.api("/api/evaluate/screen", {
          method: "POST",
          body: JSON.stringify({ screen_id: this.screen_id, now_hm: this.now_hm, weekday: this.weekday })
        });
        this.result = r;
        this.resultText = JSON.stringify(r, null, 2);
      } catch (e) { this.error = e.message; }
    }
  }
};
