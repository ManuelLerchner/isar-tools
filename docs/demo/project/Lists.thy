theory Lists
  imports Main
begin

fun rev_acc :: "'a list ⇒ 'a list ⇒ 'a list" where
  "rev_acc [] acc = acc"
| "rev_acc (x # xs) acc = rev_acc xs (x # acc)"

lemma rev_acc_rev: "rev_acc xs ys = rev xs @ ys"   
proof (induction xs arbitrary: ys)
case Nil
then show ?case by simp
next
case (Cons x xs)
then show ?case by simp
qed



lemma "rev_acc xs [] = rev xs"
  by (simp add: rev_acc_rev)

end
