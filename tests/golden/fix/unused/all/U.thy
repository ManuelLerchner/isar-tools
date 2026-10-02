theory U imports Main begin

text \<open>Facts nothing cites: a chain, a block about one fact, and two facts in one command.\<close>

section \<open>A chain\<close>

section \<open>Kept\<close>

text \<open>Two facts in one command stay: deleting the command would take the cited second one too.\<close>

lemma pair_one: "True" and pair_two: "True" by simp_all

lemma "True" using pair_two by simp

lemma [simp]: "True = True" by simp

lemma registered [intro]: "True" by simp

end
