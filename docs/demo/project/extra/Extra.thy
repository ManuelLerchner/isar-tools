theory Extra
  imports Demo.Arith
begin

lemma "length (rev_acc xs ys) = length xs + length ys"
  by (simp add: rev_acc_rev)

end
