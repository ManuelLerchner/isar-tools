theory Y imports Main begin

text \<open>Unicode in terms and in ML, where a symbol and its UTF-8 spelling differ.\<close>

lemma arrows: "A ⟶ A" "∀x. x = x" by auto
ML \<open>val s = "⇒"\<close>

lemma "True" using arrows by simp

end
