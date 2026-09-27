theory Arith
  imports Lists
begin

lemma sum_upto: "∑{0..n::nat} = n * (n + 1) div 2"
proof (induction n)
  case 0
  then show ?case by simp
next
  case (Suc n)
  then show ?case by simp
qed

lemma double_le: "∀x::nat. x ≤ 2 * x"
  sorry

end
