window.SB_VIEWS = window.SB_VIEWS || {};
window.SB_VIEWS["history-view"] = {
  template: `
  <div class="panel">
    <h2>变更历史</h2>
    <p class="lead">发布、撤屏、覆盖与台账变更同源可追溯；正式上屏记录同票附带场控单号。</p>
    <div class="row-form">
      <select v-model="action" @change="reload">
        <option value="">全部动作</option>
        <option value="publish_official">正式发布（甲）</option>
        <option value="promote_shadow">影子升正</option>
        <option value="supplement_ticket">影子补票</option>
        <option value="create">创建</option>
        <option value="patch">变更</option>
      </select>
    </div>
    <table>
      <thead><tr><th>ID</th><th>实体</th><th>动作</th><th>详情（含场控单号）</th><th>操作者</th></tr></thead>
      <tbody>
        <tr v-for="h in items" :key="h.id">
          <td>{{ h.id }}</td><td>{{ h.entity_kind }}#{{ h.entity_id }}</td>
          <td><span class="badge" :class="h.action.includes('ticket') || h.detail.includes('场控单号') ? '' : 'warn'">{{ h.action }}</span></td>
          <td>{{ h.detail }}</td><td>{{ h.actor }}</td>
        </tr>
      </tbody>
    </table>
  </div>`,
  data() { return { items: [], action: "" }; },
  async mounted() { await this.reload(); },
  methods: {
    async reload() {
      const qs = this.action ? ("?action=" + encodeURIComponent(this.action)) : "";
      this.items = (await SB.api("/api/history" + qs)).items;
    }
  }
};
