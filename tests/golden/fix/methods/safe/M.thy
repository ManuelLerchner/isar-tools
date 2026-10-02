theory M imports Main begin

text \<open>Modifiers that list nothing, and facts listed twice.\<close>

lemma empty_alone: "True" by simp
lemma empty_among: "True" by (auto simp add: TrueI)
lemma twice: "True" by (simp add: TrueI conjI)
lemma twice_attr: "True" by (simp add: TrueI[symmetric] TrueI)

lemma "True" using empty_alone empty_among twice twice_attr by simp

end
