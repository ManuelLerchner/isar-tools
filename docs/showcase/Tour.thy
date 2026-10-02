theory Tour
  imports Base
begin

text \<open>A few findings of \<^verbatim>\<open>isar check\<close>.\<close>

lemma join_comm: "a \<squnion>\<^sub>m b = b \<squnion>\<^sub>m a"
  by (simp add: join_def)

lemma join_comm_again: "x \<squnion>\<^sub>m y = y \<squnion>\<^sub>m x"
  by (simp add:)

lemma join_idem: "join a a = a"
  apply (simp add: join_def)
  done

lemma join_bound: "a \<le> a \<squnion>\<^sub>m b"
  sorry

end
