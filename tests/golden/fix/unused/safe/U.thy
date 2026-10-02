theory U imports Main begin

text \<open>Facts nothing cites are reported, never deleted: whether one is dead is a decision.\<close>

section \<open>A chain\<close>

text \<open>Only the top of the chain is cited by nothing; deleting it orphans the rest.\<close>

lemma base_fact: "True" by simp

lemma middle_fact: "True" using base_fact by simp

text \<open>The top fact, explained on its own.\<close>
lemma top_fact: "True" using middle_fact by simp

section \<open>Kept\<close>

text \<open>Two facts in one command stay: deleting the command would take the cited second one too.\<close>

lemma pair_one: "True" and pair_two: "True" by simp_all

lemma "True" using pair_two by simp

lemma [simp]: "True = True" by simp

lemma registered [intro]: "True" by simp

end
