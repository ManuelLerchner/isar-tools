theory Plan_Example
  imports Main
begin

lemma foo:
  assumes "A"
    and "B"
  shows "C"
proof -
  have h: "D"
    using assms
    by auto
  show ?thesis
    using h
    by auto
qed

end
