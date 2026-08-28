// 图谱约束与索引。节点只放图谱本体，原始文本与证据在 PostgreSQL。
// 技能重要度按时间片分片存在 REQUIRES 边上，只有能力变更用双时态（见 ADR 0005）。

CREATE CONSTRAINT role_id IF NOT EXISTS FOR (r:Role) REQUIRE r.id IS UNIQUE;
CREATE CONSTRAINT skill_id IF NOT EXISTS FOR (s:Skill) REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT competency_id IF NOT EXISTS FOR (c:Competency) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT family_id IF NOT EXISTS FOR (f:RoleFamily) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT cluster_id IF NOT EXISTS FOR (k:SkillCluster) REQUIRE k.id IS UNIQUE;
// 仓储用 MERGE (ch:CompetencyChange {id}) 写入，没有唯一约束时 MERGE 既不并发安全也走全扫描。
CREATE CONSTRAINT change_id IF NOT EXISTS FOR (c:CompetencyChange) REQUIRE c.id IS UNIQUE;

CREATE INDEX role_state IF NOT EXISTS FOR (r:Role) ON (r.state);
CREATE INDEX role_emerging IF NOT EXISTS FOR (r:Role) ON (r.is_emerging);
CREATE INDEX skill_name IF NOT EXISTS FOR (s:Skill) ON (s.name);
CREATE INDEX skill_ontology IF NOT EXISTS FOR (s:Skill) ON (s.ontology_version);

// REQUIRES 的 MERGE 键和几乎所有查询的 WHERE 都是 (period, ontology_version) 这一对，
// 所以建复合关系索引而不是两个单列索引。
CREATE INDEX requires_period_ontology IF NOT EXISTS
FOR ()-[req:REQUIRES]-() ON (req.period, req.ontology_version);

// 关系形状（供实现参考，Cypher 不声明关系 schema）：
//   (:Role)-[:IN_FAMILY]->(:RoleFamily)
//   (:Role)-[:HAS_COMPETENCY]->(:Competency)
//   (:Role)-[:HAS_CHANGE]->(:CompetencyChange)
//   (:CompetencyChange)-[:FOR_COMPETENCY]->(:Competency)
//   (:Competency)-[:COVERS]->(:Skill)
//   (:Skill)-[:PARENT_OF]->(:Skill)
//   (:Skill)-[:IN_CLUSTER]->(:SkillCluster)
//   (:Skill)-[:PREREQUISITE_OF {rule, confidence, source, active, locked}]->(:Skill)
//   (:Role)-[:REQUIRES {period, weight, posting_count, total_postings, ontology_version}]->(:Skill)
//
// 技能共现不物化成 CO_OCCURS 边：每条观测都要写 O(n²) 边，而查询和前置依赖推断
// 都能从同期 REQUIRES 现算。
