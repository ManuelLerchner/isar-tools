theory Structure imports Main begin

lemma cases_proof: "P x"
using assms proof (cases x)
case A
then show ?thesis by simp
next
case B
{
fix y
have "Q y"
by simp
}
then show ?thesis
proof -
show ?thesis sorry
qed
qed

notepad
begin
fix x
have "x = x" by simp
end

end
