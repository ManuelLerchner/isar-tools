theory Gallery
  imports Base Tour Extra
begin

lemma uncited: "length [a] = 1"
  by simp

section \<open>A heading without text\<close>

lemma join_zero: "0 \<squnion>\<^sub>m b = b \<squnion>\<^sub>m 0"
  using join_comm by simp

lemma sum_list: "foldr (\<squnion>\<^sub>m) [a, b] 0 = a \<squnion>\<^sub>m (b \<squnion>\<^sub>m 0)"
  by simp

text \<open>A locale whose header names a constant that does not exist.\<close>

locale capped =
  fixes cap :: nat
  assumes "cap \<le> missing_limit"

locale unexplained =
  fixes x :: nat

class unexplained_class =
  fixes unexplained_op :: 'a

lemma old: "old_rule = old_rule"
  by simp

text \<open>See \<open>no_such_lemma\<close>; a raw _ breaks the PDF.\<close>

text

lemma arrow: "A ⟹ A"
  by simp

lemma abandoned: "False"
  oops

lemma unclosed: "(0::nat) \<le> 1"
proof -

lemma searching: "rev [] = ([]::nat list)"
  sledgehammer
  nitpick
  by simp

thm join_def

lemma reordered: "True \<and> True"
  apply (rule conjI)
   defer
   apply simp
  back
  apply simp
  done

lemma twice: "a \<squnion>\<^sub>m b = b \<squnion>\<^sub>m a"
  by (simp add: join_def join_def)

lemma (in ordered_join) small: "bound < 11"
  using bound_small by simp

lemma citations: "Suc 0 = 1"
  using uncited join_zero sum_list old arrow searching reordered twice
  by simp

end
