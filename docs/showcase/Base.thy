theory Base
  imports Main
begin

text \<open>Declarations the other theories use.\<close>

definition join :: "nat \<Rightarrow> nat \<Rightarrow> nat" (infixl "\<squnion>\<^sub>m" 65) where
  "join a b = max a b"

abbreviation join_all :: "nat list \<Rightarrow> nat" where
  "join_all xs \<equiv> foldr (\<squnion>\<^sub>m) xs 0"

text \<open>A join of the order on \<^typ>\<open>nat\<close>.\<close>

locale ordered_join =
  fixes bound :: nat
  assumes bound_pos: "0 < bound"
    and bound_small: "bound < 10"
    and bound_even: "even bound"
begin

lemma bound_nonzero: "bound \<noteq> 0"
  using bound_pos by simp

end

end
